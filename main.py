from flask import Flask, request, jsonify, send_file, render_template_string, send_from_directory
import yt_dlp
import re
import threading
import time
from pathlib import Path
import json
from datetime import datetime
import os
import requests

app = Flask(__name__)

# Configuration
DOWNLOAD_FOLDER = os.path.join(os.getcwd(), 'public', 'downloads')
COOKIES_FILE = os.path.join(os.getcwd(), 'cookies.txt')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size

# Ensure download folder exists
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# HTML template with video listing functionality
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube Video Downloader</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            width: 100%;
            max-width: 800px;
            margin: 0 auto;
            text-align: center;
        }

        .logo {
            font-size: 2.5rem;
            color: #ff0000;
            margin-bottom: 10px;
        }

        h1 {
            color: #333;
            margin-bottom: 30px;
            font-size: 1.8rem;
            font-weight: 600;
        }

        .tabs {
            display: flex;
            margin-bottom: 30px;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }

        .tab {
            flex: 1;
            padding: 15px 20px;
            background: #f8f9fa;
            border: none;
            cursor: pointer;
            font-size: 16px;
            font-weight: 500;
            transition: all 0.3s ease;
        }

        .tab.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: block;
        }

        .form-group {
            margin-bottom: 25px;
            text-align: left;
        }

        label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 500;
        }

        input[type="url"] {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #e1e1e1;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s ease;
        }

        input[type="url"]:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .quality-group {
            margin-bottom: 25px;
        }

        .quality-options {
            display: flex;
            gap: 10px;
            justify-content: center;
            flex-wrap: wrap;
        }

        .quality-option {
            display: flex;
            align-items: center;
            gap: 5px;
        }

        input[type="radio"] {
            margin: 0;
        }

        .download-btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            width: 100%;
        }

        .download-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(102, 126, 234, 0.3);
        }

        .download-btn:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }

        .loading {
            display: none;
            margin-top: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
            color: #666;
        }

        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-right: 10px;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .error, .success {
            padding: 15px;
            border-radius: 8px;
            margin-top: 20px;
            display: none;
        }

        .error {
            background: #fee;
            color: #c33;
        }

        .success {
            background: #efe;
            color: #363;
        }

        .video-list {
            text-align: left;
        }

        .video-item {
            display: flex;
            align-items: center;
            padding: 15px;
            border: 1px solid #e1e1e1;
            border-radius: 8px;
            margin-bottom: 10px;
            transition: all 0.3s ease;
            background: #fafafa;
        }

        .video-item:hover {
            background: #f0f0f0;
            border-color: #667eea;
        }

        .video-info {
            flex: 1;
            margin-right: 15px;
        }

        .video-title {
            font-weight: 600;
            color: #333;
            margin-bottom: 5px;
            font-size: 16px;
        }

        .video-meta {
            color: #666;
            font-size: 14px;
        }

        .video-actions {
            display: flex;
            gap: 10px;
        }

        .btn-small {
            padding: 8px 15px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            text-decoration: none;
            display: inline-block;
            transition: all 0.2s ease;
        }

        .btn-download {
            background: #667eea;
            color: white;
        }

        .btn-download:hover {
            background: #5a67d8;
            transform: translateY(-1px);
        }

        .btn-delete {
            background: #e53e3e;
            color: white;
        }

        .btn-delete:hover {
            background: #c53030;
            transform: translateY(-1px);
        }

        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: #666;
        }

        .empty-state-icon {
            font-size: 3rem;
            margin-bottom: 15px;
            opacity: 0.5;
        }

        .refresh-btn {
            background: #48bb78;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            margin-bottom: 20px;
        }

        .refresh-btn:hover {
            background: #38a169;
        }

        .stats {
            display: flex;
            justify-content: space-around;
            margin-bottom: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
        }

        .stat-item {
            text-align: center;
        }

        .stat-number {
            font-size: 1.5rem;
            font-weight: bold;
            color: #667eea;
        }

        .stat-label {
            font-size: 0.9rem;
            color: #666;
        }

        .footer {
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            color: #888;
            font-size: 0.9rem;
        }

        @media (max-width: 600px) {
            .video-item {
                flex-direction: column;
                align-items: flex-start;
            }
            
            .video-actions {
                margin-top: 10px;
                width: 100%;
                justify-content: flex-end;
            }
            
            .stats {
                flex-direction: column;
                gap: 10px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">📺</div>
        <h1>YouTube Video Downloader</h1>
        
        <div class="tabs">
            <button class="tab active" onclick="switchTab('download')">Download Video</button>
            <button class="tab" onclick="switchTab('library')">Video Library</button>
        </div>
        
        <!-- Download Tab -->
        <div id="download-tab" class="tab-content active">
            <form id="downloadForm" action="/download" method="post">
                <div class="form-group">
                    <label for="url">YouTube URL:</label>
                    <input type="url" id="url" name="url" placeholder="https://www.youtube.com/watch?v=..." required>
                </div>
                
                <div class="form-group quality-group">
                    <label>Quality:</label>
                    <div class="quality-options">
                        <div class="quality-option">
                            <input type="radio" id="best" name="quality" value="best" checked>
                            <label for="best">Best</label>
                        </div>
                        <div class="quality-option">
                            <input type="radio" id="720p" name="quality" value="720p">
                            <label for="720p">720p</label>
                        </div>
                        <div class="quality-option">
                            <input type="radio" id="480p" name="quality" value="480p">
                            <label for="480p">480p</label>
                        </div>
                        <div class="quality-option">
                            <input type="radio" id="audio" name="quality" value="audio">
                            <label for="audio">Audio Only</label>
                        </div>
                    </div>
                </div>
                
                <button type="submit" class="download-btn" id="downloadBtn">
                    Download Video
                </button>
            </form>
            
            <div class="loading" id="loading">
                <div class="spinner"></div>
                Downloading video... Please wait.
            </div>
            
            <div class="error" id="error"></div>
            <div class="success" id="success"></div>
        </div>
        
        <!-- Library Tab -->
        <div id="library-tab" class="tab-content">
            <button class="refresh-btn" onclick="loadVideoList()">🔄 Refresh</button>
            
            <div class="stats" id="stats">
                <div class="stat-item">
                    <div class="stat-number" id="total-videos">0</div>
                    <div class="stat-label">Total Videos</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number" id="total-size">0 MB</div>
                    <div class="stat-label">Total Size</div>
                </div>
            </div>
            
            <div class="video-list" id="videoList">
                <div class="empty-state">
                    <div class="empty-state-icon">📁</div>
                    <p>No videos downloaded yet</p>
                    <p>Download some videos to see them here!</p>
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>Videos stored in public/downloads folder</p>
            <p>Powered by yt-dlp</p>
        </div>
    </div>

    <script>
        // Tab switching functionality
        function switchTab(tabName) {
            // Hide all tab contents
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            
            // Remove active class from all tabs
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Show selected tab content
            document.getElementById(tabName + '-tab').classList.add('active');
            
            // Add active class to clicked tab
            event.target.classList.add('active');
            
            // Load video list when switching to library tab
            if (tabName === 'library') {
                loadVideoList();
            }
        }

        // Download form functionality
        document.getElementById('downloadForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const form = this;
            const downloadBtn = document.getElementById('downloadBtn');
            const loading = document.getElementById('loading');
            const error = document.getElementById('error');
            const success = document.getElementById('success');
            
            // Reset states
            error.style.display = 'none';
            success.style.display = 'none';
            loading.style.display = 'block';
            downloadBtn.disabled = true;
            downloadBtn.textContent = 'Downloading...';
            
            // Create FormData and send request
            const formData = new FormData(form);
            
            fetch('/download', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (response.ok) {
                    return response.json().then(data => {
                        success.innerHTML = `
                            Video downloaded successfully!<br>
                            <strong>${data.title}</strong><br>
                            <small>Check the Library tab to view all downloads</small>
                        `;
                        success.style.display = 'block';
                        
                        // Clear the URL input
                        document.getElementById('url').value = '';
                        
                        // Refresh library if it's the active tab
                        if (document.getElementById('library-tab').classList.contains('active')) {
                            loadVideoList();
                        }
                    });
                } else {
                    return response.json().then(data => {
                        throw new Error(data.error || 'Download failed');
                    });
                }
            })
            .catch(err => {
                error.textContent = err.message;
                error.style.display = 'block';
            })
            .finally(() => {
                loading.style.display = 'none';
                downloadBtn.disabled = false;
                downloadBtn.textContent = 'Download Video';
            });
        });

        // Load and display video list
        function loadVideoList() {
            fetch('/api/videos')
                .then(response => response.json())
                .then(data => {
                    const videoList = document.getElementById('videoList');
                    const totalVideos = document.getElementById('total-videos');
                    const totalSize = document.getElementById('total-size');
                    
                    if (data.videos.length === 0) {
                        videoList.innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">📁</div>
                                <p>No videos downloaded yet</p>
                                <p>Download some videos to see them here!</p>
                            </div>
                        `;
                    } else {
                        videoList.innerHTML = data.videos.map(video => `
                            <div class="video-item">
                                <div class="video-info">
                                    <div class="video-title">${video.title}</div>
                                    <div class="video-meta">
                                        ${video.size} • ${video.type} • ${video.date}
                                    </div>
                                </div>
                                <div class="video-actions">
                                    <a href="/download-file/${encodeURIComponent(video.filename)}" 
                                       class="btn-small btn-download" 
                                       download="${video.filename}">
                                        📥 Download
                                    </a>
                                    <button class="btn-small btn-delete" 
                                            onclick="deleteVideo('${video.filename}')">
                                        🗑️ Delete
                                    </button>
                                </div>
                            </div>
                        `).join('');
                    }
                    
                    // Update stats
                    totalVideos.textContent = data.stats.total_files;
                    totalSize.textContent = data.stats.total_size;
                })
                .catch(err => {
                    console.error('Error loading video list:', err);
                    document.getElementById('videoList').innerHTML = `
                        <div class="error">
                            Failed to load video list. Please try refreshing.
                        </div>
                    `;
                });
        }

        // Delete video function
        function deleteVideo(filename) {
            if (!confirm('Are you sure you want to delete this video?')) {
                return;
            }
            
            fetch('/api/delete/' + encodeURIComponent(filename), {
                method: 'DELETE'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    loadVideoList(); // Refresh the list
                } else {
                    alert('Failed to delete video: ' + data.error);
                }
            })
            .catch(err => {
                alert('Error deleting video: ' + err.message);
            });
        }

        // Load video list on page load
        document.addEventListener('DOMContentLoaded', function() {
            // Load video list initially (but don't show it since download tab is active)
            loadVideoList();
        });
    </script>
</body>
</html>
"""

def is_valid_youtube_url(url):
    """Validate if the URL is a valid YouTube URL"""
    youtube_patterns = [
        r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/',
        r'(https?://)?(www\.)?m\.youtube\.com/',
        r'(https?://)?(www\.)?gaming\.youtube\.com/',
        r'(https?://)?(www\.)?music\.youtube\.com/',
        r'(https?://)?(www\.)?youtube\.googleapis\.com/'
    ]
    
    for pattern in youtube_patterns:
        if re.match(pattern, url, re.IGNORECASE):
            return True
    return False

def cleanup_old_files():
    """Clean up old downloaded files (older than 24 hours)"""
    try:
        current_time = time.time()
        for file_path in Path(DOWNLOAD_FOLDER).glob("*"):
            if file_path.is_file() and current_time - file_path.stat().st_mtime > 86400:  # 24 hours
                try:
                    file_path.unlink()
                except:
                    pass
    except:
        pass

def get_quality_format(quality):
    """Convert quality selection to yt-dlp format string"""
    quality_map = {
        'best': 'best[ext=mp4]/best',
        '720p': 'best[height<=720][ext=mp4]/best[height<=720]',
        '480p': 'best[height<=480][ext=mp4]/best[height<=480]',
        'audio': 'bestaudio[ext=m4a]/bestaudio'
    }
    return quality_map.get(quality, 'best[ext=mp4]/best')

def format_file_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def get_video_list():
    """Get list of downloaded videos with metadata"""
    videos = []
    total_size = 0
    
    try:
        for file_path in Path(DOWNLOAD_FOLDER).glob("*"):
            if file_path.is_file() and file_path.suffix.lower() in ['.mp4', '.m4a', '.webm', '.mkv']:
                try:
                    stat = file_path.stat()
                    size_bytes = stat.st_size
                    total_size += size_bytes
                    
                    # Extract title from filename (remove timestamp prefix and extension)
                    filename = file_path.name
                    title = filename
                    
                    # Try to extract title from filename pattern
                    if filename.startswith('yt_download_'):
                        parts = filename.split('_', 3)
                        if len(parts) >= 4:
                            title = parts[3].rsplit('.', 1)[0]  # Remove extension
                    
                    videos.append({
                        'filename': filename,
                        'title': title,
                        'size': format_file_size(size_bytes),
                        'size_bytes': size_bytes,
                        'type': 'Audio' if file_path.suffix.lower() == '.m4a' else 'Video',
                        'date': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                        'timestamp': stat.st_mtime
                    })
                except:
                    continue
        
        # Sort by download date (newest first)
        videos.sort(key=lambda x: x['timestamp'], reverse=True)
        
    except Exception as e:
        print(f"Error getting video list: {e}")
    
    return {
        'videos': videos,
        'stats': {
            'total_files': len(videos),
            'total_size': format_file_size(total_size)
        }
    }

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/download', methods=['POST'])
def download_video():
    try:
        url = request.form.get('url')
        quality = request.form.get('quality', 'best')
        
        if not url:
            return jsonify({'error': 'YouTube URL is required'}), 400
        
        # Debug: Log the URL being processed
        print(f"🔍 Processing URL: {url}")
        
        # Validate YouTube URL
        if not is_valid_youtube_url(url):
            return jsonify({'error': 'Please provide a valid YouTube URL'}), 400
        
        # Clean up old files in background
        threading.Thread(target=cleanup_old_files, daemon=True).start()
        
        # Generate unique filename with timestamp
        timestamp = str(int(time.time()))
        
        # Configure yt-dlp options
        ydl_opts = {
            'format': get_quality_format(quality),
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, f'yt_download_{timestamp}_%(title)s.%(ext)s'),
            'noplaylist': True,
            'extractaudio': quality == 'audio',
            'audioformat': 'm4a' if quality == 'audio' else None,
            'prefer_ffmpeg': True,
            'keepvideo': False if quality == 'audio' else True,
            'writeinfojson': False,
            'writesubtitles': False,
            # Additional options to avoid connection issues
            'socket_timeout': 30,
            'retries': 3,
            'fragment_retries': 3,
            'no_warnings': False,
            'ignoreerrors': False,
            # Enhanced anti-bot detection measures
            'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'referer': 'https://www.youtube.com/',
            'http_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
            },
            # Rate limiting and retry strategy
            'sleep_interval': 2,
            'max_sleep_interval': 10,
            'sleep_interval_subtitles': 2,
            # Additional bypass options
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls'],
                    'player_client': ['android', 'web'],
                }
            },
        }
        
        # Use cookies if available (OPTIONAL)
        if os.path.exists(COOKIES_FILE):
            ydl_opts['cookiefile'] = COOKIES_FILE
            print(f"🍪 Using cookies from: {COOKIES_FILE}")
        else:
            print("ℹ️  No cookies file found - downloading without cookies (may limit access to some videos)")
        
        # Try downloading with primary method
        video_title = "video"
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first to get title
                print(f"📺 Extracting video info from: {url}")
                info = ydl.extract_info(url, download=False)
                video_title = info.get('title', 'video')
                print(f"🎬 Video title: {video_title}")
                
                # Download the video
                print(f"⬇️  Starting download...")
                ydl.download([url])
                print(f"✅ Download completed successfully")
                
        except Exception as primary_error:
            print(f"❌ Primary method failed: {primary_error}")
            
            # Try fallback method with different settings
            print("🔄 Trying fallback method...")
            fallback_opts = ydl_opts.copy()
            fallback_opts.update({
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android'],
                        'skip': ['webpage'],
                    }
                },
                'user_agent': 'com.google.android.youtube/17.31.35 (Linux; U; Android 11) gzip',
                'sleep_interval': 5,
            })
            
            try:
                with yt_dlp.YoutubeDL(fallback_opts) as ydl_fallback:
                    print(f"📱 Trying Android client extraction...")
                    info = ydl_fallback.extract_info(url, download=False)
                    video_title = info.get('title', 'video')
                    print(f"🎬 Video title: {video_title}")
                    
                    print(f"⬇️  Starting fallback download...")
                    ydl_fallback.download([url])
                    print(f"✅ Fallback download completed successfully")
                    
            except Exception as fallback_error:
                print(f"❌ Fallback method also failed: {fallback_error}")
                # Raise the original error for better debugging
                raise primary_error
        
        # Return success response with title
        return jsonify({
            'success': True,
            'title': video_title,
            'message': 'Video downloaded successfully and saved to public folder'
        })
        
    except yt_dlp.DownloadError as e:
        error_msg = str(e)
        if "Sign in to confirm you're not a bot" in error_msg:
            return jsonify({'error': 'YouTube bot detection triggered. Please try: 1) Update your cookies.txt file with fresh login cookies, 2) Wait a few minutes before trying again, 3) Try a different video first'}), 400
        elif "HTTP Error 403: Forbidden" in error_msg:
            return jsonify({'error': 'YouTube blocked the request (403 Forbidden). Solutions: 1) Wait 10-15 minutes before trying again, 2) Update yt-dlp: pip install --upgrade yt-dlp, 3) Try a different video, 4) Use fresh cookies.txt from your browser'}), 400
        elif "This video is unavailable" in error_msg:
            return jsonify({'error': 'This video is unavailable (private, deleted, or region-blocked)'}), 400
        else:
            return jsonify({'error': f'Download error: {error_msg}'}), 400
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/api/videos')
def api_get_videos():
    """API endpoint to get list of downloaded videos"""
    return jsonify(get_video_list())

@app.route('/download-file/<filename>')
def download_file(filename):
    """Download a specific file from the public folder"""
    try:
        file_path = os.path.join(DOWNLOAD_FOLDER, filename)
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/delete/<filename>', methods=['DELETE'])
def api_delete_video(filename):
    """Delete a video file"""
    try:
        file_path = os.path.join(DOWNLOAD_FOLDER, filename)
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
        
        os.remove(file_path)
        return jsonify({'success': True, 'message': 'File deleted successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/public/downloads/<filename>')
def serve_public_file(filename):
    """Serve files from public downloads folder"""
    return send_from_directory(DOWNLOAD_FOLDER, filename)

@app.route('/health')
def health_check():
    cookies_status = "Found" if os.path.exists(COOKIES_FILE) else "Not found"
    return jsonify({
        'status': 'healthy', 
        'message': 'YouTube Downloader API is running',
        'download_folder': DOWNLOAD_FOLDER,
        'cookies_file': COOKIES_FILE,
        'cookies_status': cookies_status,
        'total_videos': len(list(Path(DOWNLOAD_FOLDER).glob("*")))
    })

if __name__ == '__main__':
    # Ensure download folder exists
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    
    # Check for cookies file
    if os.path.exists(COOKIES_FILE):
        print(f"🍪 Cookies file found: {COOKIES_FILE}")
        print(f"   This will help with restricted/private videos")
    else:
        print(f"ℹ️  No cookies file found at: {COOKIES_FILE}")
        print(f"   To use cookies, place your cookies.txt file in the project root")
        print(f"   This helps with age-restricted, private, or region-blocked videos")
    
    print(f"📁 Downloads will be stored in: {DOWNLOAD_FOLDER}")
    print(f"🌐 Access the app at: http://localhost:5000")
    print(f"📚 Video library at: http://localhost:5000 (Library tab)")
    
    # Run the Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)