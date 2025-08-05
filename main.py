import os
import shutil
import uuid
import threading
import time
from flask import Flask, request, jsonify, send_from_directory, after_this_request, render_template
import subprocess
import json

app = Flask(__name__)

TEMP_DOWNLOAD_BASE_DIR = "/tmp/yt_dlp_downloads"
COOKIE_FILE_PATH = os.environ.get('YT_DLP_COOKIE_FILE', '/etc/secrets/cookies.txt')

# Background job tracking
download_jobs = {}

if not os.path.exists(TEMP_DOWNLOAD_BASE_DIR):
    os.makedirs(TEMP_DOWNLOAD_BASE_DIR)

@app.route('/')
def home():
    return render_template('index.html')

def background_download(job_id, video_url, download_type):
    """Background download function that runs in a separate thread"""
    try:
        download_jobs[job_id]['status'] = 'processing'
        download_jobs[job_id]['message'] = 'Starting download...'
        
        specific_download_dir = download_jobs[job_id]['download_dir']
        output_template = os.path.join(specific_download_dir, "%(title)s - %(id)s.%(ext)s")
        
        # Ultra-aggressive settings for cloud deployment
        command = [
            'yt-dlp',
            '--no-warnings',
            '--quiet',  # Reduce output
            '--sleep-requests', '0.1',
            '--socket-timeout', '8',
            '--retries', '1',
            '--fragment-retries', '1',
            '--no-playlist',
            '--max-filesize', '15M',  # Even smaller limit
            '--output', output_template,
            '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        ]
        
        # Add format selection
        if download_type == 'video':
            command.extend(['-f', 'worst[ext=mp4][height<=360]/worst'])  # Lowest quality for speed
        elif download_type == 'audio':
            if shutil.which("ffmpeg"):
                command.extend(['-x', '--audio-format', 'mp3', '--audio-quality', '9'])  # Lowest quality
            else:
                command.extend(['-f', 'worstaudio[ext=m4a]/worstaudio'])
        
        # Add cookies if available
        temp_cookie_path = get_cookie_path()
        if temp_cookie_path:
            command.extend(['--cookies', temp_cookie_path])
        
        command.append(video_url)
        
        download_jobs[job_id]['message'] = 'Downloading...'
        
        # Run with very short timeout
        process = subprocess.run(command, capture_output=True, text=True, timeout=20)
        
        downloaded_files = os.listdir(specific_download_dir)
        if downloaded_files and process.returncode == 0:
            download_jobs[job_id]['status'] = 'completed'
            download_jobs[job_id]['filename'] = downloaded_files[0]
            download_jobs[job_id]['message'] = 'Download completed successfully!'
        else:
            download_jobs[job_id]['status'] = 'failed'
            download_jobs[job_id]['message'] = 'Download failed. Try a shorter video or different format.'
            download_jobs[job_id]['error'] = process.stderr[-200:] if process.stderr else 'Unknown error'
            
    except subprocess.TimeoutExpired:
        download_jobs[job_id]['status'] = 'failed'
        download_jobs[job_id]['message'] = 'Download timed out after 20 seconds. Try a very short video.'
    except Exception as e:
        download_jobs[job_id]['status'] = 'failed'
        download_jobs[job_id]['message'] = f'Error: {str(e)}'

def get_cookie_path():
    app.logger.info(f"Looking for cookies at: {COOKIE_FILE_PATH}")
    
    if COOKIE_FILE_PATH and os.path.exists(COOKIE_FILE_PATH):
        app.logger.info(f"Found cookies file at: {COOKIE_FILE_PATH}")
        # Use temp directory that's guaranteed to be writable
        temp_cookie_path = os.path.join(TEMP_DOWNLOAD_BASE_DIR, 'cookies.txt')
        try:
            shutil.copy(COOKIE_FILE_PATH, temp_cookie_path)
            app.logger.info(f"Successfully copied cookies to writable path: {temp_cookie_path}")
            return temp_cookie_path
        except Exception as e:
            app.logger.error(f"Failed to copy cookie file from {COOKIE_FILE_PATH} to {temp_cookie_path}: {e}")
            app.logger.info("Proceeding without cookies due to copy failure")
    else:
        app.logger.info(f"Cookies file not found at {COOKIE_FILE_PATH} - proceeding without cookies.")
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
            '--sleep-requests', '0.5',
            '--min-sleep-interval', '1',
            '--max-sleep-interval', '3',
            '--no-playlist'

        ]

        temp_cookie_path = get_cookie_path()
        if temp_cookie_path:
            command.extend(['--cookies', temp_cookie_path])
        else:
            app.logger.info("Proceeding without cookies.")

        command.append(video_url)

        app.logger.info(f"Running get_info command: {' '.join(command)}")
        process = subprocess.run(command, capture_output=True, text=True, check=True, timeout=15)
        video_info = json.loads(process.stdout)
        return jsonify(video_info)

    except subprocess.TimeoutExpired:
        return jsonify({
            "error": "Video info extraction timed out (15 second limit). The video might be unavailable or restricted.",
        }), 408
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
        '--sleep-requests', '0.5',
        '--min-sleep-interval', '1',
        '--max-sleep-interval', '3',
        '--no-playlist',
        '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        '--output', output_template,
        '--no-check-certificate',
        '--prefer-free-formats',
        '--max-filesize', '25M',  # Smaller limit for faster cloud deployment
        '--socket-timeout', '15',
        '--fragment-retries', '2',
        '--retries', '2',
        '--file-access-retries', '2'
    ]

    temp_cookie_path = get_cookie_path()
    if temp_cookie_path:
        command.extend(['--cookies', temp_cookie_path])
    else:
        app.logger.info("Proceeding without cookies.")

    if download_type == 'video':
        # Optimized format selection for fast cloud deployment
        command.extend(['-f', 'best[ext=mp4][height<=480][filesize<=50M]/best[height<=480]/worst[ext=mp4]/worst'])
    elif download_type == 'audio':
        # Check if ffmpeg is available
        if shutil.which("ffmpeg"):
            command.extend(['-x', '--audio-format', 'mp3', '--audio-quality', '192'])
        else:
            # Fallback: download best audio format without conversion
            app.logger.warning("FFmpeg not available, downloading audio without conversion")
            command.extend(['-f', 'bestaudio[ext=m4a]/bestaudio'])

    command.append(video_url)

    try:
        app.logger.info(f"Running download command: {' '.join(command)}")
        # Add timeout for cloud deployment (Render has ~30s request timeout)
        process = subprocess.run(command, capture_output=True, text=True, timeout=25)

        app.logger.info(f"Download stdout: {process.stdout}")
        if process.stderr:
            app.logger.info(f"Download stderr: {process.stderr}")

        downloaded_files = os.listdir(specific_download_dir)
        if not downloaded_files:
            shutil.rmtree(specific_download_dir)
            
            # Provide more specific error messages for common cloud deployment issues
            error_msg = f"yt-dlp {download_type} download failed or produced no file."
            stderr_lower = process.stderr.lower() if process.stderr else ""
            
            if "http error 429" in stderr_lower:
                error_msg = "YouTube rate limiting detected. Please wait a few minutes and try again."
            elif "unable to download webpage" in stderr_lower:
                error_msg = "Unable to access YouTube. This might be due to network restrictions or rate limiting."
            elif "ffmpeg" in stderr_lower and "not found" in stderr_lower:
                error_msg = "Audio conversion failed. FFmpeg might not be available on this server."
            elif "timeout" in stderr_lower:
                error_msg = "Download timed out. Try again with a shorter video."
            elif "file size exceeds" in stderr_lower:
                error_msg = "Video file is too large (>25MB limit). Try downloading audio instead or a shorter video."
                
            return jsonify({
                "error": error_msg,
                "returncode": process.returncode,
                "debug_info": {
                    "stdout": process.stdout[-500:] if process.stdout else "",  # Last 500 chars
                    "stderr": process.stderr[-500:] if process.stderr else "",   # Last 500 chars
                    "expected_dir": specific_download_dir
                }
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
        
    except subprocess.TimeoutExpired:
        shutil.rmtree(specific_download_dir)
        return jsonify({
            "error": "Download timed out (25 second limit). Try a shorter video or audio-only download.",
            "suggestion": "For longer videos, try downloading audio instead of video."
        }), 408
    except Exception as e:
        shutil.rmtree(specific_download_dir)
        return jsonify({
            "error": f"Unexpected error in {download_type} download",
            "details": str(e)
        }), 500

@app.route('/start_download', methods=['POST'])
def start_download():
    """Start a background download and return job ID"""
    data = request.get_json()
    video_url = data.get('url')
    download_type = data.get('type', 'audio')  # 'video' or 'audio'
    
    if not video_url:
        return jsonify({"error": "Missing 'url' parameter"}), 400
    
    if download_type not in ['video', 'audio']:
        return jsonify({"error": "Type must be 'video' or 'audio'"}), 400
    
    # Create job
    job_id = str(uuid.uuid4())
    specific_download_dir = os.path.join(TEMP_DOWNLOAD_BASE_DIR, job_id)
    os.makedirs(specific_download_dir, exist_ok=True)
    
    download_jobs[job_id] = {
        'status': 'queued',
        'message': 'Download queued...',
        'download_dir': specific_download_dir,
        'created_at': time.time(),
        'type': download_type,
        'url': video_url
    }
    
    # Start background download
    thread = threading.Thread(target=background_download, args=(job_id, video_url, download_type))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "job_id": job_id,
        "status": "queued",
        "message": "Download started in background"
    })

@app.route('/download_status/<job_id>')
def download_status(job_id):
    """Check the status of a background download"""
    if job_id not in download_jobs:
        return jsonify({"error": "Job not found"}), 404
    
    job = download_jobs[job_id]
    
    # Clean up old failed jobs
    if job['status'] in ['failed'] and time.time() - job['created_at'] > 300:  # 5 minutes
        if os.path.exists(job['download_dir']):
            shutil.rmtree(job['download_dir'])
        del download_jobs[job_id]
        return jsonify({"error": "Job expired"}), 404
    
    response = {
        "status": job['status'],
        "message": job['message'],
        "type": job['type']
    }
    
    if job['status'] == 'completed':
        response['download_url'] = f"/download_file/{job_id}"
    elif job['status'] == 'failed' and 'error' in job:
        response['error_details'] = job['error']
    
    return jsonify(response)

@app.route('/download_file/<job_id>')
def download_file(job_id):
    """Download the completed file"""
    if job_id not in download_jobs:
        return jsonify({"error": "Job not found"}), 404
    
    job = download_jobs[job_id]
    
    if job['status'] != 'completed':
        return jsonify({"error": "Download not completed"}), 400
    
    if 'filename' not in job:
        return jsonify({"error": "File not found"}), 404
    
    # Clean up after download
    @after_this_request
    def cleanup(response):
        try:
            if os.path.exists(job['download_dir']):
                shutil.rmtree(job['download_dir'])
            if job_id in download_jobs:
                del download_jobs[job_id]
        except Exception as e:
            app.logger.error(f"Cleanup error: {e}")
        return response
    
    return send_from_directory(
        directory=job['download_dir'], 
        path=job['filename'], 
        as_attachment=True
    )

# Legacy endpoints for backward compatibility
@app.route('/download_video', methods=['GET'])
def download_video_route():
    return jsonify({
        "error": "This endpoint is deprecated. Use /start_download with POST instead.",
        "example": {
            "method": "POST",
            "url": "/start_download",
            "body": {"url": "youtube_url", "type": "video"}
        }
    }), 410

@app.route('/download_audio', methods=['GET'])
def download_audio_route():
    return jsonify({
        "error": "This endpoint is deprecated. Use /start_download with POST instead.",
        "example": {
            "method": "POST", 
            "url": "/start_download",
            "body": {"url": "youtube_url", "type": "audio"}
        }
    }), 410

@app.route('/test_download')
def test_download():
    """Test endpoint with a known working video"""
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Roll - should always work
    return handle_download(test_url, 'audio')

@app.route('/jobs')
def list_jobs():
    """List all active download jobs (for debugging)"""
    jobs_info = {}
    for job_id, job in download_jobs.items():
        jobs_info[job_id] = {
            "status": job['status'],
            "message": job['message'],
            "type": job['type'],
            "created_at": job['created_at'],
            "age_seconds": int(time.time() - job['created_at']),
            "url": job['url'][:50] + "..." if len(job['url']) > 50 else job['url']
        }
    
    return jsonify({
        "total_jobs": len(download_jobs),
        "jobs": jobs_info
    })

@app.route('/health')
def health_check():
    """Health check endpoint for debugging deployment issues"""
    
    health_info = {
        "status": "healthy",
        "temp_dir": TEMP_DOWNLOAD_BASE_DIR,
        "temp_dir_exists": os.path.exists(TEMP_DOWNLOAD_BASE_DIR),
        "temp_dir_writable": os.access(TEMP_DOWNLOAD_BASE_DIR, os.W_OK) if os.path.exists(TEMP_DOWNLOAD_BASE_DIR) else False,
        "cookie_file_env": COOKIE_FILE_PATH,
        "cookie_file_exists": os.path.exists(COOKIE_FILE_PATH) if COOKIE_FILE_PATH else False,
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "yt_dlp_version": None,
        "active_jobs": len(download_jobs),
        "background_download_system": "enabled"
    }
    
    # Check yt-dlp version
    try:
        result = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            health_info["yt_dlp_version"] = result.stdout.strip()
    except:
        health_info["yt_dlp_version"] = "Error checking version"
    
    return jsonify(health_info)

def cleanup_old_jobs():
    """Clean up old download jobs and directories"""
    current_time = time.time()
    jobs_to_remove = []
    
    for job_id, job in download_jobs.items():
        # Remove jobs older than 1 hour
        if current_time - job['created_at'] > 3600:
            jobs_to_remove.append(job_id)
            try:
                if os.path.exists(job['download_dir']):
                    shutil.rmtree(job['download_dir'])
            except Exception as e:
                app.logger.error(f"Error cleaning up job {job_id}: {e}")
    
    for job_id in jobs_to_remove:
        del download_jobs[job_id]
    
    app.logger.info(f"Cleaned up {len(jobs_to_remove)} old jobs")

# Start background cleanup thread
def start_cleanup_thread():
    def cleanup_loop():
        while True:
            time.sleep(1800)  # Run every 30 minutes
            cleanup_old_jobs()
    
    cleanup_thread = threading.Thread(target=cleanup_loop)
    cleanup_thread.daemon = True
    cleanup_thread.start()

if __name__ == '__main__':
    # Start cleanup thread
    start_cleanup_thread()
    
    port = int(os.environ.get('PORT', 8080))
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)