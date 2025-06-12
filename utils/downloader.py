import os
import threading
import uuid
import random
import string
import yt_dlp
import traceback

from config import VIDEO_DIR, SERVER_URL, SUPPORTED_PLATFORMS
from utils.platform_helper import detect_platform
from utils.status_manager import update_status
from utils.history_manager import save_to_history

COOKIE_DIR = os.path.join(os.path.dirname(__file__), "..", "cookies")
GLOBAL_PROXY = os.getenv("YTS_PROXY")

_download_threads = {}
_download_locks = {}

def generate_filename():
    return f"YTSx_{''.join(random.choices(string.ascii_lowercase + string.digits, k=12))}"

def write_cookie_file_from_header(cookie_header: str) -> str:
    path = f"/tmp/yts_cookie_{uuid.uuid4().hex}.txt"
    with open(path, "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for pair in cookie_header.split(';'):
            try:
                key, value = pair.strip().split("=", 1)
                f.write(f".domain.com\tTRUE\t/\tFALSE\t0\t{key}\t{value}\n")
            except:
                continue
    return path

def get_platform_cookie_file(platform: str) -> str:
    filename = f"{platform[:2]}_cookies.txt"
    path = os.path.join(COOKIE_DIR, filename)
    return path if os.path.exists(path) else None

def extract_metadata(url, download_id=None, headers=None):
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
    cookie_path = None
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'forcejson': True,
        'noplaylist': True,
        'extract_flat': False,
        'progress_hooks': [lambda _: cancel_event.is_set() and (_ for _ in ()).throw(Exception("Cancelled"))],
    }

    try:
        if headers and 'Cookie' in headers:
            cookie_path = write_cookie_file_from_header(headers['Cookie'])
            ydl_opts['cookiefile'] = cookie_path
            ydl_opts['http_headers'] = headers
            print(f"[COOKIES] ✅ Using header-based cookie file: {cookie_path}")
        else:
            platform_cookie = get_platform_cookie_file(platform)
            if platform_cookie:
                ydl_opts['cookiefile'] = platform_cookie
                print(f"[COOKIES] ✅ Using default platform cookie file: {platform_cookie}")
            else:
                print(f"[COOKIES] ⚠️ No cookie used for platform: {platform}")

        if GLOBAL_PROXY:
            ydl_opts['proxy'] = GLOBAL_PROXY

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

    except Exception as e:
        update_status(download_id, {"status": "cancelled"})
        return {"error": str(e), "download_id": download_id}
    finally:
        if cookie_path and os.path.exists(cookie_path):
            os.remove(cookie_path)

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
        return {"error": "❌ Format parse failed.", "download_id": download_id}

def start_download(url, resolution, headers=None, bandwidth_limit=None):
    download_id = str(uuid.uuid4())
    filename = generate_filename()
    output_path = os.path.join(VIDEO_DIR, f"{filename}.mp4")
    platform = detect_platform(url)
    cookie_path = None
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
            ydl_opts = {
                'format': f"bestvideo[ext=mp4][height={height}]+bestaudio[ext=m4a]/best[ext=mp4][height={height}]",
                'merge_output_format': 'mp4',
                'outtmpl': output_path,
                'noplaylist': True,
                'quiet': True,
                'progress_hooks': [lambda d: _progress_hook(d, download_id, cancel_event)],
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4'
                }]
            }

            if headers and 'Cookie' in headers:
                cookie_path = write_cookie_file_from_header(headers['Cookie'])
                ydl_opts['cookiefile'] = cookie_path
                ydl_opts['http_headers'] = headers
                print(f"[COOKIES] ✅ Using header-based cookie file: {cookie_path}")
            else:
                platform_cookie = get_platform_cookie_file(platform)
                if platform_cookie:
                    ydl_opts['cookiefile'] = platform_cookie
                    print(f"[COOKIES] ✅ Using default platform cookie file: {platform_cookie}")
                else:
                    print(f"[COOKIES] ⚠️ No cookie used for platform: {platform}")

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
            update_status(download_id, {"status": "error", "error": error_msg})

        except Exception as e:
            traceback.print_exc()
            update_status(download_id, {
                "status": "error",
                "error": "❌ Unexpected error."
            })

        finally:
            if cookie_path and os.path.exists(cookie_path):
                os.remove(cookie_path)

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

get_video_info = extract_metadata