# services/tt_service.py

import os
import uuid
import yt_dlp
import tempfile
import threading
import random
import string
import traceback

from config import SERVER_URL
from utils.platform_helper import merge_headers_with_cookie, get_cookie_file_for_platform
from utils.status_manager import update_status
from utils.history_manager import save_to_history
from utils.download_registry import register_thread, register_cancel_event

# Constants
VIDEO_DIR = 'static/videos'
AUDIO_DIR = 'static/audios'
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)
TEMP_COOKIE_SUFFIX = "_cookie.txt"
GLOBAL_PROXY = os.getenv("YTS_PROXY")

# --- Helpers ---

def generate_filename(prefix="tt"):
    return f"{prefix}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=12))}"

def _prepare_cookie_file(headers):
    if headers and "Cookie" in headers:
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=TEMP_COOKIE_SUFFIX, mode='w')
        temp.write(headers["Cookie"])
        temp.close()
        print(f"[TT COOKIES] Using temp cookie: {temp.name}")
        return temp.name
    fallback = get_cookie_file_for_platform("tiktok")
    if fallback:
        print(f"[TT COOKIES] Using fallback cookie: {fallback}")
    return fallback

def _progress_hook(d, download_id, cancel_event):
    if cancel_event.is_set():
        raise Exception("Cancelled by user")
    if d.get("status") != "downloading":
        return
    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
    downloaded = d.get("downloaded_bytes", 0)
    percent = int((downloaded / total) * 100)
    speed = d.get("speed", 0)
    speed_str = f"{round(speed / 1024, 1)}KB/s" if speed else "0KB/s"
    update_status(download_id, {
        "status": "downloading",
        "progress": percent,
        "speed": speed_str
    })

# --- Metadata Extraction ---

def extract_tt_metadata(url, headers=None, download_id=None):
    download_id = download_id or str(uuid.uuid4())
    cancel_event = threading.Event()
    register_cancel_event(download_id, cancel_event)
    update_status(download_id, {"status": "extracting", "progress": 0, "speed": "0KB/s"})

    try:
        merged_headers = merge_headers_with_cookie(headers or {}, "tiktok")
        cookie_file = _prepare_cookie_file(headers)

        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "forcejson": True,
            "noplaylist": True,
            "extract_flat": False,
            "http_headers": merged_headers,
            "progress_hooks": [lambda _: cancel_event.is_set() and (_ for _ in ()).throw(Exception("Cancelled"))],
        }

        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file
        if GLOBAL_PROXY:
            ydl_opts["proxy"] = GLOBAL_PROXY

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = info.get("formats", [])
        duration = info.get("duration", 0)
        resolutions, sizes, seen = [], [], set()

        for f in formats:
            height = f.get("height")
            if not height or f.get("vcodec") == "none":
                continue
            label = f"{height}p"
            if label in seen:
                continue
            seen.add(label)
            size = f.get("filesize") or f.get("filesize_approx")
            size_str = f"{round(size / 1024 / 1024, 2)}MB" if size else "Unknown"
            resolutions.append(label)
            sizes.append(size_str)

        update_status(download_id, {"status": "ready"})

        return {
            "download_id": download_id,
            "platform": "tiktok",
            "title": info.get("title", "Untitled"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader", "TikTok"),
            "duration": duration,
            "video_url": url,
            "resolutions": resolutions,
            "sizes": sizes,
            "audioFormats": [{
                "label": "Original",
                "abr": "Original",
                "size": sizes[0] if sizes else "Unknown"
            }],
            "audio_dubs": []
        }

    except Exception as e:
        print(f"[TT ❌ METADATA ERROR] {e}")
        traceback.print_exc()
        update_status(download_id, {"status": "error", "error": "❌ Failed to extract metadata"})
        return {"error": "❌ Failed to extract metadata", "download_id": download_id}

# --- Audio Download ---

def start_tt_audio_download(url, headers=None, audio_quality='192'):
    download_id = str(uuid.uuid4())
    filename = generate_filename("ttaudio")
    output_path = os.path.join(AUDIO_DIR, f"{filename}.mp3")
    cancel_event = threading.Event()
    register_cancel_event(download_id, cancel_event)

    def run():
        update_status(download_id, {
            "status": "starting", "progress": 0, "speed": "0KB/s", "audio_url": None
        })

        try:
            merged_headers = merge_headers_with_cookie(headers or {}, "tiktok")
            cookie_file = _prepare_cookie_file(headers)

            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": output_path,
                "quiet": True,
                "noplaylist": True,
                "http_headers": merged_headers,
                "progress_hooks": [lambda d: _progress_hook(d, download_id, cancel_event)],
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": audio_quality
                }]
            }

            if cookie_file:
                ydl_opts["cookiefile"] = cookie_file
            if GLOBAL_PROXY:
                ydl_opts["proxy"] = GLOBAL_PROXY

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            if cancel_event.is_set():
                update_status(download_id, {"status": "cancelled"})
                return

            update_status(download_id, {
                "status": "completed",
                "progress": 100,
                "speed": "0KB/s",
                "audio_url": f"{SERVER_URL}/audios/{os.path.basename(output_path)}"
            })

            save_to_history({
                "id": download_id,
                "title": os.path.basename(output_path),
                "resolution": "MP3",
                "status": "completed",
                "size": round(os.path.getsize(output_path) / 1024 / 1024, 2)
            })

        except Exception as e:
            traceback.print_exc()
            update_status(download_id, {"status": "error", "error": "❌ TikTok audio download failed"})

    thread = threading.Thread(target=run, daemon=True)
    register_thread(download_id, thread)
    thread.start()
    return download_id

# --- Video Download ---

def start_tt_video_download(url, resolution, headers=None, audio_lang=None, bandwidth_limit=None):
    download_id = str(uuid.uuid4())
    filename = generate_filename("tt")
    output_path = os.path.join(VIDEO_DIR, f"{filename}.mp4")
    cancel_event = threading.Event()
    register_cancel_event(download_id, cancel_event)

    def parse_bandwidth_limit(limit):
        if not limit:
            return None
        if isinstance(limit, (int, float)):
            return limit * 1024
        if isinstance(limit, str):
            limit = limit.strip().upper()
            units = {"K": 1024, "M": 1024**2, "G": 1024**3}
            for suffix, factor in units.items():
                if limit.endswith(suffix):
                    return float(limit[:-1]) * factor
        return None

    def run():
        update_status(download_id, {
            "status": "starting", "progress": 0, "speed": "0KB/s", "video_url": None
        })

        try:
            merged_headers = merge_headers_with_cookie(headers or {}, "tiktok")
            cookie_file = _prepare_cookie_file(headers)
            height = resolution.replace("p", "")

            ydl_opts = {
                "format": f"bestvideo[height={height}]+bestaudio/best[height={height}]",
                "outtmpl": output_path,
                "quiet": True,
                "noplaylist": True,
                "merge_output_format": "mp4",
                "http_headers": merged_headers,
                "progress_hooks": [lambda d: _progress_hook(d, download_id, cancel_event)],
                "postprocessors": [{
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4"
                }]
            }

            if cookie_file:
                ydl_opts["cookiefile"] = cookie_file
            if GLOBAL_PROXY:
                ydl_opts["proxy"] = GLOBAL_PROXY

            rate = parse_bandwidth_limit(bandwidth_limit)
            if rate:
                ydl_opts["ratelimit"] = rate

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            if cancel_event.is_set():
                update_status(download_id, {"status": "cancelled"})
                return

            update_status(download_id, {
                "status": "completed",
                "progress": 100,
                "speed": "0KB/s",
                "video_url": f"{SERVER_URL}/videos/{os.path.basename(output_path)}"
            })

            save_to_history({
                "id": download_id,
                "title": os.path.basename(output_path),
                "resolution": resolution,
                "status": "completed",
                "size": round(os.path.getsize(output_path) / 1024 / 1024, 2)
            })

        except Exception as e:
            traceback.print_exc()
            update_status(download_id, {"status": "error", "error": "❌ TikTok video download failed"})

    thread = threading.Thread(target=run, daemon=True)
    register_thread(download_id, thread)
    thread.start()
    return download_id
