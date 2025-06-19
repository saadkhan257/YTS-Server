# services/ig_service.py

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

VIDEO_DIR = 'static/videos'
AUDIO_DIR = 'static/audios'
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

GLOBAL_PROXY = os.getenv("YTS_PROXY")
TEMP_COOKIE_SUFFIX = "_cookie.txt"

# --- Helpers ---

def generate_filename(prefix="ig"):
    return f"{prefix}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=12))}"

def _prepare_cookie_file(headers):
    if headers and "Cookie" in headers:
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=TEMP_COOKIE_SUFFIX, mode='w')
        temp.write(headers["Cookie"])
        temp.close()
        return temp.name
    return get_cookie_file_for_platform("instagram")

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

# --- Metadata ---

def extract_ig_metadata(url, headers=None, download_id=None):
    import collections

    download_id = download_id or str(uuid.uuid4())
    cancel_event = threading.Event()
    register_cancel_event(download_id, cancel_event)
    update_status(download_id, {"status": "extracting", "progress": 0, "speed": "0KB/s"})

    try:
        merged_headers = merge_headers_with_cookie(headers or {}, "instagram")
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
        duration = info.get("duration") or 0

        resolution_map = collections.OrderedDict()
        seen = set()

        for fmt in formats:
            ext = fmt.get("ext")
            vcodec = fmt.get("vcodec")
            acodec = fmt.get("acodec")
            height = fmt.get("height")
            tbr = fmt.get("tbr")
            fmt_id = fmt.get("format_id")

            if not height or vcodec == "none" or ext != "mp4":
                continue

            label = f"{height}p"
            if label in seen:
                continue
            seen.add(label)

            size = fmt.get("filesize") or fmt.get("filesize_approx") or 0
            if not size and tbr:
                size = (tbr * 1000 / 8) * duration  # estimate in bytes
            size_str = f"{round(size / 1024 / 1024, 2)}MB" if size else "Unknown"

            resolution_map[label] = {
                "label": label,
                "height": height,
                "ext": ext,
                "vcodec": vcodec,
                "acodec": acodec,
                "format_id": fmt_id,
                "size": size_str
            }

        resolutions = list(resolution_map.keys())
        sizes = [v["size"] for v in resolution_map.values()]
        videoFormats = list(resolution_map.values())

        # Instagram usually has muxed formats, so we treat audio as part of main video
        audioFormats = [{
            "label": "Original",
            "abr": "N/A",
            "ext": "mp4",
            "size": sizes[0] if sizes else "Unknown",
            "format_id": videoFormats[0].get("format_id") if videoFormats else None
        }]

        update_status(download_id, {"status": "ready", "progress": 0})

        return {
            "download_id": download_id,
            "platform": "instagram",
            "title": info.get("title", "Untitled"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader", "Instagram"),
            "duration": duration,
            "video_url": url,
            "resolutions": resolutions,
            "sizes": sizes,
            "videoFormats": videoFormats,
            "audioFormats": audioFormats,
            "audio_dubs": []
        }

    except Exception as e:
        traceback.print_exc()
        update_status(download_id, {"status": "error", "error": f"❌ Metadata extraction failed: {e}"} )
        return {"error": str(e), "download_id": download_id}

def start_ig_audio_download(url, headers=None, audio_quality="192"):
    download_id = str(uuid.uuid4())
    filename = generate_filename("ig_audio")
    output_path = os.path.join(AUDIO_DIR, f"{filename}.mp3")
    cancel_event = threading.Event()
    register_cancel_event(download_id, cancel_event)

    def run():
        update_status(download_id, {
            "status": "starting",
            "progress": 0,
            "speed": "0KB/s",
            "audio_url": None
        })

        try:
            merged_headers = merge_headers_with_cookie(headers or {}, "instagram")
            cookie_file = _prepare_cookie_file(headers)

            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": output_path,
                "quiet": True,
                "noplaylist": True,
                "http_headers": merged_headers,
                "cookiefile": cookie_file,
                "proxy": GLOBAL_PROXY,
                "progress_hooks": [lambda d: _progress_hook(d, download_id, cancel_event)],
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": audio_quality
                }],
                "user_agent": "Mozilla/5.0 (X11; Linux x86_64)",
                "retries": 3,
                "overwrites": True
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            if cancel_event.is_set():
                update_status(download_id, {"status": "cancelled"})
                return

            audio_url = f"{SERVER_URL}/audios/{os.path.basename(output_path)}"
            size_mb = round(os.path.getsize(output_path) / 1024 / 1024, 2)

            update_status(download_id, {
                "status": "completed",
                "progress": 100,
                "speed": "0KB/s",
                "audio_url": audio_url
            })

            save_to_history({
                "id": download_id,
                "title": os.path.basename(output_path),
                "resolution": f"{audio_quality}K MP3",
                "status": "completed",
                "size": size_mb
            })

        except Exception as e:
            traceback.print_exc()
            update_status(download_id, {
                "status": "error",
                "error": f"❌ Instagram audio download failed: {str(e)[:200]}"
            })

    thread = threading.Thread(target=run, daemon=True)
    register_thread(download_id, thread)
    thread.start()
    return download_id

# --- Video Download ---

def start_ig_video_download(url, resolution, headers=None, audio_lang=None, bandwidth_limit=None):
    download_id = str(uuid.uuid4())
    filename = generate_filename("ig_vid")
    output_path = os.path.join(VIDEO_DIR, f"{filename}.mp4")
    cancel_event = threading.Event()
    register_cancel_event(download_id, cancel_event)

    def parse_bandwidth_limit(limit):
        try:
            if isinstance(limit, (int, float)):
                return limit * 1024
            s = str(limit).strip().upper()
            unit = s[-1]
            val = float(s[:-1])
            return val * {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}.get(unit, 1)
        except:
            return None

    def run():
        update_status(download_id, {
            "status": "starting",
            "progress": 0,
            "speed": "0KB/s",
            "video_url": None
        })

        try:
            merged_headers = merge_headers_with_cookie(headers or {}, "instagram")
            cookie_file = _prepare_cookie_file(headers)
            height = resolution.replace("p", "")

            # Main format string
            video_fmt = f"bestvideo[ext=mp4][height={height}]"
            audio_fmt = "bestaudio[ext=m4a]"
            if audio_lang:
                audio_fmt += f"[language^{audio_lang}]"

            format_string = f"{video_fmt}+{audio_fmt}/best[ext=mp4][height={height}]/best"

            ydl_opts = {
                "format": format_string,
                "outtmpl": output_path,
                "quiet": True,
                "noplaylist": True,
                "merge_output_format": "mp4",
                "http_headers": merged_headers,
                "cookiefile": cookie_file,
                "proxy": GLOBAL_PROXY,
                "progress_hooks": [lambda d: _progress_hook(d, download_id, cancel_event)],
                "postprocessors": [{
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4"
                }],
                "user_agent": "Mozilla/5.0 (X11; Linux x86_64)",
                "retries": 3,
                "overwrites": True
            }

            rl = parse_bandwidth_limit(bandwidth_limit)
            if rl:
                ydl_opts["ratelimit"] = rl

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            if cancel_event.is_set():
                update_status(download_id, {"status": "cancelled"})
                return

            size_mb = round(os.path.getsize(output_path) / 1024 / 1024, 2)
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
                "size": size_mb
            })

        except Exception as e:
            traceback.print_exc()
            update_status(download_id, {
                "status": "error",
                "error": f"❌ Instagram video download failed: {str(e)[:200]}"
            })

    thread = threading.Thread(target=run, daemon=True)
    register_thread(download_id, thread)
    thread.start()
    return download_id
