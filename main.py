import os
import shutil
import uuid
from flask import Flask, request, jsonify, send_from_directory, after_this_request
import subprocess
import json

app = Flask(__name__)

TEMP_DOWNLOAD_BASE_DIR = "/tmp/yt_dlp_downloads"
COOKIE_FILE_PATH = os.environ.get('YT_DLP_COOKIE_FILE')

if not os.path.exists(TEMP_DOWNLOAD_BASE_DIR):
    os.makedirs(TEMP_DOWNLOAD_BASE_DIR)

@app.route('/')
def home():
    return """
    <h1>yt-dlp on Render POC</h1>
    <p>Use the following endpoints:</p>
    <ul>
        <li><code>/get_info?url=YOUR_YOUTUBE_URL</code> - to get video metadata as JSON.</li>
        <li><code>/download_video?url=YOUR_YOUTUBE_URL</code> - to download the best quality video.</li>
        <li><code>/download_audio?url=YOUR_YOUTUBE_URL</code> - to download the best quality audio as MP3.</li>
    </ul>
    """

def get_cookie_path():
    if COOKIE_FILE_PATH and os.path.exists(COOKIE_FILE_PATH):
        temp_cookie_path = '/etc/secrets/cookies.txt'
        try:
            shutil.copy(COOKIE_FILE_PATH, temp_cookie_path)
            app.logger.info(f"Copied cookie file to writable path: {temp_cookie_path}")
            return temp_cookie_path
        except Exception as e:
            app.logger.error(f"Failed to copy cookie file: {e}")
    else:
        app.logger.warning("COOKIE_FILE_PATH not set or file does not exist.")
    return None

@app.route('/get_info', methods=['GET'])
def get_info():
    video_url = request.args.get('url')
    if not video_url:
        return jsonify({"error": "Missing 'url' parameter."}), 400

    try:
        command = [
            'yt-dlp',
            '-J',
            '--no-warnings',
            '--verbose',
            '--sleep-requests', '1.25',
            '--min-sleep-interval', '60',
            '--max-sleep-interval', '90'
            '--no-check-formats',
            '--force-generic-extractor',
            '--no-playlist'

        ]

        temp_cookie_path = get_cookie_path()
        if temp_cookie_path:
            command.extend(['--cookies', temp_cookie_path])
        else:
            app.logger.info("Proceeding without cookies.")

        command.append(video_url)

        app.logger.info(f"Running get_info command: {' '.join(command)}")
        process = subprocess.run(command, capture_output=True, text=True, check=True)
        video_info = json.loads(process.stdout)
        return jsonify(video_info)

    except subprocess.CalledProcessError as e:
        app.logger.error(f"get_info yt-dlp failed: {e.stderr}")
        return jsonify({
            "error": "yt-dlp command failed for get_info",
            "returncode": e.returncode,
            "stderr": e.stderr,
            "stdout": e.stdout
        }), 500
    except json.JSONDecodeError as e:
        return jsonify({
            "error": "Failed to parse yt-dlp JSON output for get_info",
            "details": str(e),
            "raw_stdout": getattr(process, 'stdout', 'N/A')
        }), 500
    except Exception as e:
        return jsonify({
            "error": "An unexpected error occurred during get_info",
            "details": str(e)
        }), 500

def handle_download(video_url, download_type):
    if not video_url:
        return jsonify({"error": "Missing 'url' parameter"}), 400

    download_id = str(uuid.uuid4())
    specific_download_dir = os.path.join(TEMP_DOWNLOAD_BASE_DIR, download_id)
    os.makedirs(specific_download_dir, exist_ok=True)

    output_template = os.path.join(specific_download_dir, "%(title)s - %(id)s.%(ext)s")
    command = [
        'yt-dlp',
        '--no-warnings',
        '--verbose',
        '--sleep-requests', '1.25',
        '--min-sleep-interval', '60',
        '--max-sleep-interval', '90',
        '--no-check-formats',
        '--force-generic-extractor',
        '--no-playlist',
        '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
        '--output', output_template
    ]

    temp_cookie_path = get_cookie_path()
    if temp_cookie_path:
        command.extend(['--cookies', temp_cookie_path])
    else:
        app.logger.info("Proceeding without cookies.")

    if download_type == 'video':
        command.extend(['-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best'])
    elif download_type == 'audio':
        command.extend(['-x', '--audio-format', 'mp3', '--audio-quality', '0'])

    command.append(video_url)

    try:
        app.logger.info(f"Running download command: {' '.join(command)}")
        process = subprocess.run(command, capture_output=True, text=True)

        app.logger.info(f"Download stdout: {process.stdout}")
        if process.stderr:
            app.logger.info(f"Download stderr: {process.stderr}")

        downloaded_files = os.listdir(specific_download_dir)
        if not downloaded_files:
            shutil.rmtree(specific_download_dir)
            return jsonify({
                "error": f"yt-dlp {download_type} download failed or produced no file.",
                "returncode": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr,
                "expected_dir": specific_download_dir
            }), 500

        downloaded_filename = downloaded_files[0]

        if process.returncode != 0 and "Read-only file system" in process.stderr:
            app.logger.warning("Cookie write error ignored; file likely downloaded.")
        elif process.returncode != 0:
            shutil.rmtree(specific_download_dir)
            return jsonify({
                "error": f"yt-dlp {download_type} download failed.",
                "returncode": process.returncode,
                "stderr": process.stderr,
                "stdout": process.stdout
            }), 500

        @after_this_request
        def cleanup(response):
            try:
                shutil.rmtree(specific_download_dir)
                app.logger.info(f"Cleaned up {specific_download_dir}")
            except Exception as e:
                app.logger.error(f"Cleanup error: {e}")
            return response

        return send_from_directory(directory=specific_download_dir, path=downloaded_filename, as_attachment=True)

    except Exception as e:
        shutil.rmtree(specific_download_dir)
        return jsonify({
            "error": f"Unexpected error in {download_type} download",
            "details": str(e)
        }), 500

@app.route('/download_video', methods=['GET'])
def download_video_route():
    video_url = request.args.get('url')
    return handle_download(video_url, 'video')

@app.route('/download_audio', methods=['GET'])
def download_audio_route():
    video_url = request.args.get('url')
    return handle_download(video_url, 'audio')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)