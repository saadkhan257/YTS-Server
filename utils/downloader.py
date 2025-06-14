import os
import threading
import uuid
import random
import string
import yt_dlp
import traceback
import tempfile

from config import VIDEO_DIR, SERVER_URL
from utils.platform_helper import detect_platform, merge_headers_with_cookie
from utils.status_manager import update_status
from utils.history_manager import save_to_history

GLOBAL_PROXY = os.getenv("YTS_PROXY")

_download_threads = {}
_download_locks = {}

def generate_filename():
    return f"YTSx_{''.join(random.choices(string.ascii_lowercase + string.digits, k=12))}"

def _prepare_cookie_file(headers, platform):
    if headers and "Cookie" in headers:
        temp = tempfile.NamedTemporaryFile(delete=False, suffix="_cookie.txt")
        temp.write(headers["Cookie"].encode())
        temp.close()
        return temp.name
    # No user header cookie → fallback to default platform cookie file
    merged = merge_headers_with_cookie({}, platform)
    if "Cookie" in merged:
        temp = tempfile.NamedTemporaryFile(delete=False, suffix="_cookie.txt")
        temp.write(merged["Cookie"].encode())
        temp.close()
        return temp.name
    return None

def extract_metadata(url, headers=None, download_id=None):
    if not download_id:
        download_id = str(uuid.uuid4())

    cancel_event = threading.Event()
    _download_locks[download_id] = cancel_event

    update_status(download_id, {
        "status": "extracting",
        "progress": 0,
        "speed": "0KB/s",
    })

    platform = detect_platform(url)
    print(f"[EXTRACT] Extracting from {platform.capitalize()}: {url}")

    merged_headers = merge_headers_with_cookie(headers or {}, platform)
    cookie_file = _prepare_cookie_file(headers, platform)

    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'forcejson': True,
        'noplaylist': True,
        'extract_flat': False,
        'http_headers': merged_headers,
        'progress_hooks': [lambda _: cancel_event.is_set() and (_ for _ in ()).throw(Exception("Cancelled"))],
    }

    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file

    if GLOBAL_PROXY:
        ydl_opts['proxy'] = GLOBAL_PROXY

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"[ERROR] Metadata extraction failed: {e}")
        update_status(download_id, {"status": "cancelled"})
        return {"error": str(e), "download_id": download_id}

    try:
        resolutions, sizes, seen = [], [], set()
        duration = info.get("duration", 0)

        for f in info.get("formats", []):
            ext = f.get("ext")
            height = f.get("height")
            vcodec = f.get("vcodec", "")
            if not height or vcodec == "none" or ext != "mp4":
                continue

            label = f"{height}p"
            if label in seen:
                continue
            seen.add(label)

            size = f.get("filesize") or f.get("filesize_approx")
            if not size and duration and f.get("tbr"):
                size = (f["tbr"] * 1000 / 8) * duration
            size_str = f"{round(size / 1024 / 1024, 2)}MB" if size else "Unknown"

            resolutions.append(label)
            sizes.append(size_str)

        update_status(download_id, {"status": "ready"})

        return {
            "download_id": download_id,
            "platform": platform,
            "title": info.get("title", "Untitled"),
            "thumbnail": info.get("thumbnail", ""),
            "uploader": info.get("uploader"),
            "duration": duration,
            "video_url": url,
            "resolutions": resolutions,
            "sizes": sizes
        }

    except Exception as e:
        print(f"[ERROR] Format parsing failed: {e}")
        return {"error": "❌ Format parse failed.", "download_id": download_id}

def start_download(url, resolution, bandwidth_limit=None, headers=None):
    download_id = str(uuid.uuid4())
    filename = generate_filename()
    output_path = os.path.join(VIDEO_DIR, f"{filename}.mp4")
    platform = detect_platform(url)
    cancel_event = threading.Event()
    _download_locks[download_id] = cancel_event

    def run():
        update_status(download_id, {
            "status": "starting",
            "progress": 0,
            "speed": "0KB/s",
            "video_url": None
        })

        try:
            height = resolution.replace("p", "")
            merged_headers = merge_headers_with_cookie(headers or {}, platform)
            cookie_file = _prepare_cookie_file(headers, platform)

            ydl_opts = {
                'format': f"bestvideo[ext=mp4][height={height}]+bestaudio[ext=m4a]/best[ext=mp4][height={height}]",
                'merge_output_format': 'mp4',
                'outtmpl': output_path,
                'noplaylist': True,
                'quiet': True,
                'http_headers': merged_headers,
                'progress_hooks': [lambda d: _progress_hook(d, download_id, cancel_event)],
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4'
                }]
            }

            if cookie_file:
                ydl_opts['cookiefile'] = cookie_file

            if bandwidth_limit:
                ydl_opts['ratelimit'] = bandwidth_limit * 1024

            if GLOBAL_PROXY:
                ydl_opts['proxy'] = GLOBAL_PROXY

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            if cancel_event.is_set():
                update_status(download_id, {"status": "cancelled"})
                return

            if not os.path.exists(output_path):
                raise FileNotFoundError("Download succeeded but file not found.")

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

        except yt_dlp.utils.DownloadError as e:
            error_msg = "❌ Download failed."
            if "Sign in" in str(e) or "captcha" in str(e).lower():
                error_msg = "🔐 Login or CAPTCHA required."
            elif "unsupported url" in str(e).lower():
                error_msg = "❌ Unsupported or invalid video link."
            print(f"[YT-DLP ERROR] {e}")
            update_status(download_id, {"status": "error", "error": error_msg})

        except Exception as e:
            print(f"[UNEXPECTED ERROR] {e}")
            traceback.print_exc()
            update_status(download_id, {
                "status": "error",
                "error": "❌ Unexpected error."
            })

    thread = threading.Thread(target=run, daemon=True)
    _download_threads[download_id] = thread
    thread.start()
    return download_id

def _progress_hook(d, download_id, cancel_event):
    if cancel_event.is_set():
        raise Exception("Cancelled by user")

    if d.get("status") != "downloading":
        return

    total = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
    downloaded = d.get('downloaded_bytes', 0)
    percent = int((downloaded / total) * 100)
    speed = d.get('speed', 0)
    speed_str = f"{round(speed / 1024, 1)}KB/s" if speed else "0KB/s"

    update_status(download_id, {
        "status": "downloading",
        "progress": percent,
        "speed": speed_str
    })

def cancel_download(download_id):
    cancel_event = _download_locks.get(download_id)
    if cancel_event:
        cancel_event.set()
        update_status(download_id, {"status": "cancelled"})
        return True
    return False

def pause_download(download_id):
    return False

def resume_download(download_id):
    return False

def get_video_info(url, headers=None, download_id=None):
    return extract_metadata(url, headers=headers, download_id=download_id)
