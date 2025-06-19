import os
import uuid
import yt_dlp
import tempfile
import traceback
import random
import string
import threading

from config import VIDEO_DIR, SERVER_URL
from utils.platform_helper import merge_headers_with_cookie, get_cookie_file_for_platform
from utils.status_manager import update_status
from utils.history_manager import save_to_history
from utils.download_registry import register_thread, register_cancel_event

# Constants
AUDIO_DIR = 'static/audios'
os.makedirs(AUDIO_DIR, exist_ok=True)

SUPPORTED_AUDIO_FORMATS = {"m4a", "mp3", "aac", "opus"}
MP4_EXTENSIONS = {"mp4", "m4v", "mov"}
GLOBAL_PROXY = os.getenv("YTS_PROXY")
TEMP_COOKIE_SUFFIX = "_cookie.txt"

_download_threads = {}
_download_locks = {}

def generate_filename(prefix="YTSx"):
    return f"{prefix}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=12))}"

def _prepare_cookie_file(headers, platform):
    if headers and "Cookie" in headers:
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=TEMP_COOKIE_SUFFIX, mode='w')
        temp.write(headers["Cookie"])
        temp.close()
        print(f"[COOKIES] Using temporary cookie file: {temp.name}")
        return temp.name
    return get_cookie_file_for_platform(platform)

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

def extract_yt_metadata(url, headers=None, download_id=None):
    download_id = download_id or str(uuid.uuid4())
    cancel_event = threading.Event()
    _download_locks[download_id] = cancel_event
    update_status(download_id, {"status": "extracting", "progress": 0, "speed": "0KB/s"})

    platform = "youtube"
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
        'cookiefile': cookie_file if cookie_file else None,
        'proxy': GLOBAL_PROXY if GLOBAL_PROXY else None,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = info.get("formats", [])
        duration = info.get("duration", 0)
        seen = set()
        resolutions, sizes = [], []
        audio_formats = {}
        audio_dubs = []
        seen_dubs = set()

        for f in formats:
            if f.get("vcodec") == "none" and f.get("acodec") != "none" and f.get("abr") and f.get("ext") in SUPPORTED_AUDIO_FORMATS:
                label = f"{int(f['abr'])}K"
                if label not in audio_formats:
                    size = f.get("filesize") or f.get("filesize_approx")
                    if not size and f.get("tbr"):
                        size = (f["tbr"] * 1000 / 8) * duration
                    size_str = f"{round(size / 1024 / 1024, 2)}MB" if size else "Unknown"
                    audio_formats[label] = {
                        "label": label,
                        "abr": f.get("abr"),
                        "size": size_str
                    }

            # Audio dubs
            lang = f.get("language") or f.get("language_code")
            if lang and f.get("vcodec") == "none":
                lang_lower = lang.lower()
                if lang_lower not in seen_dubs:
                    seen_dubs.add(lang_lower)
                    audio_dubs.append({
                        "lang": lang_lower,
                        "label": lang.upper()
                    })

            # Video formats
            if not f.get("height") or f.get("vcodec") == "none" or f.get("ext") not in MP4_EXTENSIONS:
                continue
            label = f"{f['height']}p"
            if label in seen:
                continue
            seen.add(label)
            size = f.get("filesize") or f.get("filesize_approx")
            if not size and f.get("tbr"):
                size = (f["tbr"] * 1000 / 8) * duration
            size_str = f"{round(size / 1024 / 1024, 2)}MB" if size else "Unknown"
            resolutions.append(label)
            sizes.append(size_str)

        update_status(download_id, {"status": "ready"})

        return {
            "download_id": download_id,
            "platform": "youtube",
            "title": info.get("title", "Untitled"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader", "YouTube"),
            "duration": duration,
            "video_url": url,
            "resolutions": resolutions,
            "sizes": sizes,
            "audioFormats": list(audio_formats.values()),
            "audio_dubs": audio_dubs
        }

    except Exception as e:
        traceback.print_exc()
        print(f"[YT ❌ METADATA ERROR] {str(e)}")
        update_status(download_id, {"status": "error", "error": "❌ Failed to extract metadata"})
        return {"error": "❌ Failed to extract metadata", "download_id": download_id}


# --- Audio Download ---

def start_yt_audio_download(url, headers=None, audio_quality='192'):
    download_id = str(uuid.uuid4())
    filename = generate_filename("audio")
    output_path = os.path.join(AUDIO_DIR, f"{filename}.mp3")
    cancel_event = threading.Event()
    _download_locks[download_id] = cancel_event

    def run():
        update_status(download_id, {
            "status": "starting", "progress": 0, "speed": "0KB/s", "audio_url": None
        })

        try:
            merged_headers = merge_headers_with_cookie(headers or {}, "youtube")
            cookie_file = _prepare_cookie_file(headers, "youtube")

            ydl_opts = {
                'format': f"bestaudio[abr={audio_quality}]/bestaudio",
                'outtmpl': output_path,
                'quiet': True,
                'noplaylist': True,
                'merge_output_format': 'mp3',
                'http_headers': merged_headers,
                'progress_hooks': [lambda d: _progress_hook(d, download_id, cancel_event)],
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': audio_quality,
                }],
            }

            if cookie_file:
                ydl_opts['cookiefile'] = cookie_file
            if GLOBAL_PROXY:
                ydl_opts['proxy'] = GLOBAL_PROXY

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
                "resolution": f"{audio_quality}K",
                "status": "completed",
                "size": round(os.path.getsize(output_path) / 1024 / 1024, 2)
            })

        except Exception as e:
            traceback.print_exc()
            update_status(download_id, {"status": "error", "error": "❌ Audio download failed"})

    thread = threading.Thread(target=run, daemon=True)
    _download_threads[download_id] = thread
    thread.start()
    return download_id

# --- Video Download ---

def start_yt_video_download(url, resolution, headers=None, audio_lang=None, bandwidth_limit=None):
    download_id = str(uuid.uuid4())
    filename = generate_filename()
    output_path = os.path.join(VIDEO_DIR, f"{filename}.mp4")
    cancel_event = threading.Event()
    _download_locks[download_id] = cancel_event
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
            merged_headers = merge_headers_with_cookie(headers or {}, "youtube")
            cookie_file = _prepare_cookie_file(headers, "youtube")
            height = resolution.replace("p", "")

            video_fmt = f"bestvideo[ext=mp4][height={height}]"
            audio_fmt = f"bestaudio[ext=m4a]"
            if audio_lang:
                audio_fmt += f"[language^{audio_lang}]"

            ydl_opts = {
                'format': f"{video_fmt}+{audio_fmt}/best[ext=mp4][height={height}]",
                'outtmpl': output_path,
                'quiet': True,
                'noplaylist': True,
                'merge_output_format': 'mp4',
                'http_headers': merged_headers,
                'progress_hooks': [lambda d: _progress_hook(d, download_id, cancel_event)],
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4'
                }],
            }

            if cookie_file:
                ydl_opts['cookiefile'] = cookie_file
            if GLOBAL_PROXY:
                ydl_opts['proxy'] = GLOBAL_PROXY

            rate = parse_bandwidth_limit(bandwidth_limit)
            if rate:
                ydl_opts['ratelimit'] = rate

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
            update_status(download_id, {"status": "error", "error": "❌ Video download failed"})

            thread = threading.Thread(target=run, daemon=True)
            register_thread(download_id, thread)
            thread.start()
            return download_id