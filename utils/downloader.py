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


# --- [ABOVE THIS LINE IS ALL YOUR ORIGINAL IMPORTS & CONSTANTS] ---
AUDIO_DIR = 'static/audios'
os.makedirs(AUDIO_DIR, exist_ok=True)
# ...

# --- Save as Audio (MP3) Download ---

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

        try:
            merged_headers = merge_headers_with_cookie(headers or {}, platform)
            cookie_file = _prepare_cookie_file(headers, platform)

            # Try to prefer matching abr, else fallback to bestaudio
            abr_format = f"bestaudio[abr={audio_quality}]"
            fallback_format = "bestaudio"
            format_selector = f"{abr_format}/{fallback_format}"

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
                print(f"[AUDIO DL] 🎵 Downloading audio from {url} (quality: {audio_quality}K)")
                result = ydl.download([url])
            elapsed = time.time() - start_time
            print(f"[AUDIO DL] ✅ Finished in {round(elapsed, 2)}s")

            if cancel_event.is_set():
                update_status(download_id, {"status": "cancelled"})
                return

            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise FileNotFoundError("Audio download succeeded but file not found or empty.")

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

        except yt_dlp.utils.DownloadError as e:
            msg = str(e).lower()
            error_msg = (
                "❌ Format not available for selected quality." if "requested format not available" in msg else
                "🔐 Login required or session expired." if "sign in" in msg else
                "❌ Audio download failed."
            )
            print(f"[AUDIO DL ❌] {e}")
            update_status(download_id, {"status": "error", "error": error_msg})

        except Exception as e:
            print(f"[AUDIO ERROR ❌] {e}")
            traceback.print_exc()
            update_status(download_id, {"status": "error", "error": "❌ Audio download failed unexpectedly."})

    thread = threading.Thread(target=run, daemon=True)
    _download_threads[download_id] = thread
    thread.start()
    return download_id


# --- [Rest of your downloader.py remains unchanged below] ---

# Proxy setup
GLOBAL_PROXY = os.getenv("YTS_PROXY") or None
_download_threads = {}
_download_locks = {}

# Constants
TEMP_COOKIE_SUFFIX = "_cookie.txt"
MP4_EXTENSIONS = {"mp4", "m4v", "mov"}
SUPPORTED_AUDIO_FORMATS = {"m4a", "mp3", "aac", "opus"}
MAX_RETRIES = 3

# --- Utility Functions ---

def generate_filename(prefix="YTSx"):
    return f"{prefix}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=12))}"

def _prepare_cookie_file(headers, platform):
    if headers and "Cookie" in headers:
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=TEMP_COOKIE_SUFFIX, mode='w')
        temp.write(headers["Cookie"])
        temp.close()
        print(f"[COOKIES] ✨ Using header-based cookie file: {temp.name}")
        return temp.name

    fallback = get_cookie_file_for_platform(platform)
    if fallback:
        print(f"[COOKIES] ✅ Using fallback cookie file: {fallback}")
        return fallback

    print(f"[COOKIES] ⚠️ No cookie used for platform: {platform}")
    return None

# --- Metadata Extraction ---

def extract_metadata(url, headers=None, download_id=None):
    if not download_id:
        download_id = str(uuid.uuid4())

    cancel_event = threading.Event()
    _download_locks[download_id] = cancel_event
    update_status(download_id, {
        "status": "extracting", "progress": 0, "speed": "0KB/s"
    })

    platform = detect_platform(url)
    merged_headers = merge_headers_with_cookie(headers or {}, platform)
    cookie_file = _prepare_cookie_file(headers, platform)

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "forcejson": True,
        "noplaylist": True,
        "extract_flat": False,
        "no_warnings": True,
        "http_headers": merged_headers,
        "progress_hooks": [lambda d: cancel_event.is_set() and (_ for _ in ()).throw(Exception("Cancelled"))],
        "extractor_args": {
            "youtube": ["player_client=web", "disable_polymer=True"]
        }
    }

    if cookie_file:
        ydl_opts["cookiefile"] = cookie_file
    if GLOBAL_PROXY:
        ydl_opts["proxy"] = GLOBAL_PROXY

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            print("✅ [EXTRACTED] yt-dlp successfully fetched metadata")
    except Exception as e:
        print(f"❌ [YTDLP FAILED] {e}")
        if platform == "tiktok":
            try:
                info = extract_info_with_selenium(url, headers=headers)
                print("🔥 [SELENIUM FALLBACK] TikTok metadata extracted!")
            except Exception as se:
                update_status(download_id, {"status": "error", "error": str(se)})
                return {"error": str(se), "download_id": download_id}
        else:
            update_status(download_id, {"status": "error", "error": str(e)})
            return {"error": str(e), "download_id": download_id}

    try:
        formats = info.get("formats", [])
        duration = info.get("duration", 0)
        title = info.get("title", "Untitled")
        uploader = info.get("uploader", platform.upper())
        thumbnail = info.get("thumbnail")
        is_live = info.get("is_live") or False

        resolutions = {}
        audios = {}
        dubs = []

        seen_video = set()
        seen_audio = set()
        codec_map = {}

        # 🎙️ Audio Dubs
        audio_tracks = info.get("audio_tracks") or []
        for track in audio_tracks:
            lang_code = track.get("language_code") or track.get("language") or "und"
            label = lang_code.upper()
            if label not in [d["label"] for d in dubs]:
                dubs.append({
                    "language": lang_code.lower(),
                    "label": label,
                    "name": track.get("name") or label,
                    "autoselect": track.get("autoselect", False)
                })

        # 🧠 Format Parsing
        for f in formats:
            ext = f.get("ext")
            acodec = f.get("acodec")
            vcodec = f.get("vcodec")
            format_id = f.get("format_id")
            height = f.get("height")
            width = f.get("width")
            fps = f.get("fps") or 30
            abr = f.get("abr")
            tbr = f.get("tbr")
            filesize = f.get("filesize") or f.get("filesize_approx")

            if not filesize and tbr and duration:
                filesize = (tbr * 1000 / 8) * duration

            size_str = f"{round(filesize / 1024 / 1024, 2)}MB" if filesize else "Unknown"

            # 🎧 Audio-Only Formats
            if vcodec == "none" and acodec != "none" and abr and ext in SUPPORTED_AUDIO_FORMATS:
                label = f"{int(abr)}K"
                if label not in seen_audio:
                    audios[label] = {
                        "label": label,
                        "abr": abr,
                        "format_id": format_id,
                        "ext": ext,
                        "size": size_str,
                        "acodec": acodec
                    }
                    seen_audio.add(label)

            # 📺 Video Formats
            elif vcodec != "none" and height and ext == "mp4":
                label = f"{height}p"
                codec_key = f"{vcodec}_{fps}"
                if label not in seen_video or codec_map.get(label, {}).get("fps", 0) < fps:
                    resolutions[label] = {
                        "label": label,
                        "format_id": format_id,
                        "height": height,
                        "width": width,
                        "fps": fps,
                        "size": size_str,
                        "vcodec": vcodec,
                        "is_dash": f.get("is_dash", False)
                    }
                    seen_video.add(label)
                    codec_map[label] = {"vcodec": vcodec, "fps": fps}

        # 🚀 Final Result
        result = {
            "download_id": download_id,
            "title": title,
            "uploader": uploader,
            "thumbnail": thumbnail,
            "duration": duration,
            "is_live": is_live,
            "resolutions": dict(sorted(resolutions.items(), key=lambda x: int(x[0].replace("p", "")), reverse=True)),
            "audios": dict(sorted(audios.items(), key=lambda x: int(x[0].replace("K", "")), reverse=True)),
            "dubs": sorted(dubs, key=lambda x: x["label"])
        }

        update_status(download_id, {"status": "ready", "metadata": result})
        return result

    except Exception as e:
        print(f"❌ [METADATA PARSE ERROR] {e}")
        traceback.print_exc()
        update_status(download_id, {"status": "error", "error": "Metadata parse failed."})
        return {"error": "Metadata parse failed", "download_id": download_id}



# --- Video Download ---

def start_download(url, resolution, bandwidth_limit=None, headers=None, audio_lang=None):
    def parse_bandwidth_limit(limit):
        if not limit:
            return None
        if isinstance(limit, (int, float)):
            return limit * 1024  # KB to Bytes
        if isinstance(limit, str):
            limit = limit.strip().upper()
            multiplier = 1
            if limit.endswith("K"):
                multiplier = 1024
                limit = limit[:-1]
            elif limit.endswith("M"):
                multiplier = 1024 * 1024
                limit = limit[:-1]
            elif limit.endswith("G"):
                multiplier = 1024 * 1024 * 1024
                limit = limit[:-1]
            try:
                return float(limit) * multiplier
            except:
                return None
        return None

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

            # Desktop user-agent to force DASH manifest access
            merged_headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            })

            # 🎯 Exact format logic (video + audio with resolution and language)
            base_video = f"bestvideo[ext=mp4][vcodec^=avc1][height={height}]"
            base_audio = f"bestaudio[ext=m4a][acodec^=mp4a]"
            if audio_lang:
                base_audio += f"[language={audio_lang.lower()}]"

            fallback_format = f"best[ext=mp4][height={height}]/best"
            final_format = f"{base_video}+{base_audio}/{fallback_format}"

            ydl_opts = {
                'format': final_format,
                'outtmpl': output_path,
                'quiet': True,
                'noplaylist': True,
                'merge_output_format': 'mp4',
                'http_headers': merged_headers,
                'cookiefile': cookie_file,
                'progress_hooks': [lambda d: _progress_hook(d, download_id, cancel_event)],
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4'
                }],
                'player_client': 'web',
                'allow_unplayable_formats': False,
                'concurrent_fragment_downloads': 4,
                'retries': 3,
                'extractor_args': {
                    'youtube': ['player_client=web', 'disable_polymer=True', 'no_check_certificate=True']
                },
                'force_keyframes_at_cuts': True,
                'prefer_ffmpeg': True,
                'verbose': True  # optional: remove this if not debugging
            }

            parsed_limit = parse_bandwidth_limit(bandwidth_limit)
            if parsed_limit:
                ydl_opts['ratelimit'] = parsed_limit

            if GLOBAL_PROXY:
                ydl_opts['proxy'] = GLOBAL_PROXY

            print(f"[🔰 YTDLP START] Format: {final_format}")
            start_time = time.time()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            elapsed = time.time() - start_time
            print(f"[✅ YTDLP DONE] Duration: {round(elapsed, 2)}s")

            if cancel_event.is_set():
                update_status(download_id, {"status": "cancelled"})
                return

            for i in range(20):
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    break
                print(f"[WAIT] Waiting for file to finalize... {i}")
                time.sleep(0.5)

            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise FileNotFoundError("Download succeeded but file not found or empty.")

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
            msg = str(e).lower()
            if "drm" in msg:
                error_msg = "🔐 Video is DRM protected."
            elif "sabr" in msg or "adaptive formats" in msg:
                error_msg = "⚠️ Video uses adaptive streaming or SABR blocks."
            elif "sign in" in msg or "captcha" in msg:
                error_msg = "🔐 Login or CAPTCHA required."
            elif "unsupported url" in msg:
                error_msg = "❌ Unsupported or invalid video link."
            elif "no video formats" in msg:
                error_msg = "❌ Exact format not available."
            else:
                error_msg = "❌ Download failed."
            print(f"[YT-DLP ERROR] {e}")
            update_status(download_id, {"status": "error", "error": error_msg})

        except Exception as e:
            print(f"[UNEXPECTED ERROR] {e}")
            traceback.print_exc()
            update_status(download_id, {"status": "error", "error": "❌ Unexpected error."})

    thread = threading.Thread(target=run, daemon=True)
    _download_threads[download_id] = thread
    thread.start()
    return download_id

# --- Progress Hook & Controls ---

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

def pause_download(download_id):
    return False

def resume_download(download_id):
    return False

def get_video_info(url, headers=None, download_id=None):
    return extract_metadata(url, headers=headers, download_id=download_id)