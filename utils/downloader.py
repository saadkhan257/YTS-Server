import os
import re
import threading
import uuid
import random
import string
import yt_dlp
import traceback
import tempfile
import time
import mimetypes
import json

from config import VIDEO_DIR, SERVER_URL
from utils.platform_helper import (
    detect_platform,
    merge_headers_with_cookie,
    get_cookie_file_for_platform
)
from utils.status_manager import update_status
from utils.history_manager import save_to_history
from services.tiktok_service import extract_info_with_selenium

# --- Directories ---
AUDIO_DIR = 'static/audios'
os.makedirs(AUDIO_DIR, exist_ok=True)

# --- Globals ---
GLOBAL_PROXY = os.getenv("YTS_PROXY") or None
_download_threads = {}
_download_locks = {}

# --- Constants ---
TEMP_COOKIE_SUFFIX = "_cookie.txt"
MP4_EXTENSIONS = {"mp4", "m4v", "mov"}
SUPPORTED_AUDIO_FORMATS = {"m4a", "mp3", "aac", "opus"}

# --- Utility ---
def generate_filename(prefix="YTSx"):
    return f"{prefix}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=12))}"

def _prepare_cookie_file(headers, platform):
    if headers and "Cookie" in headers:
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=TEMP_COOKIE_SUFFIX, mode='w')
        temp.write(headers["Cookie"])
        temp.close()
        print(f"[COOKIES] ✨ Header-based cookie: {temp.name}")
        return temp.name

    fallback = get_cookie_file_for_platform(platform)
    if fallback:
        print(f"[COOKIES] ✅ Fallback cookie: {fallback}")
        return fallback

    print(f"[COOKIES] ⚠️ No cookie used for platform: {platform}")
    return None

# --- Audio Download ---
def start_audio_download(url, headers=None, audio_quality='192'):
    download_id = str(uuid.uuid4())
    filename = generate_filename(prefix="audio")
    output_path = os.path.join(AUDIO_DIR, f"{filename}.mp3")
    platform = detect_platform(url)
    cancel_event = threading.Event()
    _download_locks[download_id] = cancel_event

    def run():
        update_status(download_id, {
            "status": "starting",
            "progress": 0,
            "speed": "0KB/s",
            "audio_url": None
        })

        temp_cookie = None
        try:
            merged_headers = merge_headers_with_cookie(headers or {}, platform)
            cookie_file = _prepare_cookie_file(headers, platform)
            if cookie_file and cookie_file.endswith(TEMP_COOKIE_SUFFIX):
                temp_cookie = cookie_file

            format_selector = f"bestaudio[abr={audio_quality}]/bestaudio"

            ydl_opts = {
                'format': format_selector,
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

            start_time = time.time()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print(f"[AUDIO DL] Downloading audio from {url}")
                ydl.download([url])
            elapsed = time.time() - start_time

            if cancel_event.is_set():
                update_status(download_id, {"status": "cancelled"})
                return

            if not os.path.exists(output_path):
                raise FileNotFoundError("Audio file not found after download.")

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

            print(f"[AUDIO DL ✅] Done in {round(elapsed, 2)}s")

        except Exception as e:
            print(f"[AUDIO ERROR] {e}")
            traceback.print_exc()
            update_status(download_id, {"status": "error", "error": "❌ Audio download failed."})
        finally:
            if temp_cookie and os.path.exists(temp_cookie):
                os.unlink(temp_cookie)

    thread = threading.Thread(target=run, daemon=True)
    _download_threads[download_id] = thread
    thread.start()
    return download_id

# --- Metadata Extraction ---
def extract_metadata(url, headers=None, download_id=None):
    if not download_id:
        download_id = str(uuid.uuid4())

    cancel_event = threading.Event()
    _download_locks[download_id] = cancel_event

    update_status(download_id, {
        "status": "extracting",
        "progress": 0,
        "speed": "0KB/s"
    })

    platform = detect_platform(url)
    print(f"[EXTRACT] Platform: {platform.upper()} | URL: {url}")
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
        if platform == "tiktok":
            try:
                info = extract_info_with_selenium(url, headers=headers)
                print(f"[SELENIUM ✅] Extracted metadata")
            except Exception as se:
                update_status(download_id, {"status": "error", "error": str(se)})
                return {"error": str(se), "download_id": download_id}
        else:
            update_status(download_id, {"status": "error", "error": str(e)})
            return {"error": str(e), "download_id": download_id}

    try:
        formats = info.get("formats", [])
        duration = info.get("duration", 0)
        seen_res, seen_dubs, seen_audio = set(), set(), set()
        resolutions, sizes, dubs, audios = [], [], [], {}

        for f in formats:
            acodec, vcodec, ext = f.get("acodec"), f.get("vcodec"), f.get("ext")
            abr, lang_code = f.get("abr"), f.get("language") or f.get("language_code")
            height, tbr = f.get("height"), f.get("tbr")
            filesize = f.get("filesize") or f.get("filesize_approx")

            if vcodec == "none" and acodec != "none" and abr and ext in SUPPORTED_AUDIO_FORMATS:
                label = f"{int(abr)}K"
                if label not in seen_audio:
                    seen_audio.add(label)
                    est = filesize or (tbr * 1000 / 8) * duration if tbr else 0
                    size_str = f"{round(est / 1024 / 1024, 2)}MB" if est else "Unknown"
                    audios[label] = {
                        "label": label,
                        "abr": abr,
                        "size": size_str
                    }

            if lang_code and acodec != "none" and vcodec == "none":
                lang = lang_code.lower()
                if lang not in seen_dubs:
                    seen_dubs.add(lang)
                    dubs.append({
                        "lang": lang,
                        "label": lang.upper()
                    })

            if height and vcodec != "none" and ext in MP4_EXTENSIONS:
                label = f"{height}p"
                if label not in seen_res:
                    seen_res.add(label)
                    est = filesize or (tbr * 1000 / 8) * duration if tbr else 0
                    size_str = f"{round(est / 1024 / 1024, 2)}MB" if est else "Unknown"
                    resolutions.append(label)
                    sizes.append(size_str)

        update_status(download_id, {"status": "ready"})

        return {
            "download_id": download_id,
            "platform": platform,
            "title": info.get("title", "Untitled"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader", platform),
            "duration": duration,
            "video_url": url,
            "resolutions": resolutions,
            "sizes": sizes,
            "audio_dubs": dubs,
            "audioFormats": list(audios.values()),
        }

    except Exception as e:
        print(f"[FORMAT ERROR] {e}")
        update_status(download_id, {"status": "error", "error": "❌ Failed to parse formats."})
        return {"error": "❌ Failed to parse formats.", "download_id": download_id}

# --- Video Download ---
def start_download(url, resolution, bandwidth_limit=None, headers=None, audio_lang=None):
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
            if bandwidth_limit:
                ydl_opts['ratelimit'] = bandwidth_limit * 1024
            if GLOBAL_PROXY:
                ydl_opts['proxy'] = GLOBAL_PROXY

            start_time = time.time()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print(f"[YTDLP] Starting download: {url}")
                ydl.download([url])
            elapsed = time.time() - start_time

            if cancel_event.is_set():
                update_status(download_id, {"status": "cancelled"})
                return

            for _ in range(20):
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    break
                time.sleep(0.5)

            if not os.path.exists(output_path):
                raise FileNotFoundError("Video file not found after download.")

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

            print(f"[YTDLP ✅] Done in {round(elapsed, 2)}s")

        except yt_dlp.utils.DownloadError as e:
            msg = str(e).lower()
            err = (
                "🔐 Login or CAPTCHA required." if "sign in" in msg or "captcha" in msg else
                "❌ Unsupported or invalid video link." if "unsupported url" in msg else
                "❌ Download failed."
            )
            update_status(download_id, {"status": "error", "error": err})
        except Exception as e:
            print(f"[UNEXPECTED ERROR] {e}")
            traceback.print_exc()
            update_status(download_id, {"status": "error", "error": "❌ Unexpected error."})

    thread = threading.Thread(target=run, daemon=True)
    _download_threads[download_id] = thread
    thread.start()
    return download_id

# --- Progress + Control ---
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

def cancel_download(download_id):
    cancel_event = _download_locks.get(download_id)
    if cancel_event:
        cancel_event.set()
        update_status(download_id, {"status": "cancelled"})
        return True
    return False

def pause_download(download_id): return False
def resume_download(download_id): return False
def get_video_info(url, headers=None, download_id=None):
    return extract_metadata(url, headers=headers, download_id=download_id)
