import os
import threading
import uuid
import yt_dlp
import traceback
import time
import json

from config import VIDEO_DIR, AUDIO_DIR, SERVER_URL, GLOBAL_PROXY
from utils.platform_helper import (
    detect_platform,
    merge_headers_with_cookie,
    get_cookie_file_for_platform
)
from utils.status_manager import update_status
from utils.history_manager import save_to_history
from utils.vid_to_mp3_converter import convert_to_mp3

_download_threads = {}
_download_locks = {}

MP4_EXTENSIONS = ("mp4", "m4v", "mov")


def generate_filename():
    return uuid.uuid4().hex


def _prepare_cookie_file(headers, platform):
    if headers and headers.get("Cookie"):
        return None  # Inline cookie overrides file
    cookie_path = get_cookie_file_for_platform(platform)
    return cookie_path if os.path.exists(cookie_path) else None


def extract_metadata(url, headers=None, download_id=None):
    download_id = download_id or str(uuid.uuid4())
    platform = detect_platform(url)

    update_status(download_id, {"status": "extracting", "progress": 0})

    try:
        merged_headers = merge_headers_with_cookie(headers or {}, platform)
        cookie_file = _prepare_cookie_file(headers, platform)

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "dump_single_json": True,
            "extract_flat": False,
            "http_headers": merged_headers
        }

        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file
        if GLOBAL_PROXY:
            ydl_opts["proxy"] = GLOBAL_PROXY

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = info.get("formats", [])
        duration = info.get("duration") or 1  # Avoid division by zero

        seen = set()
        audios = {}
        dubs = []
        resolutions = []
        sizes = []

        for f in formats:
            acodec = f.get("acodec")
            vcodec = f.get("vcodec")
            ext = f.get("ext")

            # AUDIO only
            if vcodec == "none" and acodec != "none":
                abr = f.get("abr") or 0
                if abr in audios:
                    continue
                size = f.get("filesize") or f.get("filesize_approx")
                if not size and f.get("tbr"):
                    size = (f["tbr"] * 1000 / 8) * duration
                size_str = f"{round(size / 1024 / 1024, 2)}MB" if size else "Unknown"
                audios[abr] = {
                    "label": f"{int(abr)} kbps",
                    "abr": abr,
                    "size": size_str
                }

            # Audio dubs
            lang = f.get("language") or f.get("language_code")
            if lang and acodec != "none" and vcodec == "none":
                key = lang.lower()
                if key not in [d["lang"] for d in dubs]:
                    dubs.append({
                        "lang": key,
                        "label": key.upper()
                    })

            # VIDEO only
            if f.get("height") and vcodec != "none" and ext in MP4_EXTENSIONS:
                label = f"{f['height']}p"
                if label not in seen:
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
            "platform": platform,
            "title": info.get("title", "Untitled"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader") or platform,
            "duration": duration,
            "video_url": url,
            "resolutions": resolutions,
            "sizes": sizes,
            "audio_dubs": dubs,
            "audioFormats": list(audios.values()),
        }

    except Exception as e:
        print(f"[METADATA ERROR] {e}")
        traceback.print_exc()
        update_status(download_id, {"status": "error", "error": "❌ Failed to extract metadata."})
        return {"error": "❌ Failed to extract metadata.", "download_id": download_id}


def start_download(url, resolution=None, bandwidth_limit=None, headers=None, audio_lang=None, audio_only=False):
    download_id = str(uuid.uuid4())
    filename = generate_filename()
    video_path = os.path.join(VIDEO_DIR, f"{filename}.mp4")
    audio_path = os.path.join(AUDIO_DIR, f"{filename}.mp3")
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
            merged_headers = merge_headers_with_cookie(headers or {}, platform)
            cookie_file = _prepare_cookie_file(headers, platform)

            if audio_only:
                format_selector = "bestaudio"
            else:
                height = resolution.replace("p", "") if resolution else "720"
                video_fmt = f"bestvideo[ext=mp4][height={height}]"
                audio_fmt = f"bestaudio[ext=m4a]"
                if audio_lang:
                    audio_fmt += f"[language^{audio_lang}]"
                format_selector = f"{video_fmt}+{audio_fmt}/best[ext=mp4][height={height}]"

            ydl_opts = {
                'format': format_selector,
                'outtmpl': video_path,
                'quiet': True,
                'noplaylist': True,
                'merge_output_format': 'mp4',
                'http_headers': merged_headers,
                'progress_hooks': [lambda d: _progress_hook(d, download_id, cancel_event)],
                'postprocessors': []
            }

            if audio_only:
                ydl_opts['postprocessors'].append({
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192'
                })

            if cookie_file:
                ydl_opts["cookiefile"] = cookie_file
            if bandwidth_limit:
                ydl_opts['ratelimit'] = bandwidth_limit * 1024
            if GLOBAL_PROXY:
                ydl_opts["proxy"] = GLOBAL_PROXY

            start_time = time.time()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print(f"[YT-DLP] Downloading from {url}")
                ydl.download([url])
            elapsed = time.time() - start_time
            print(f"[YT-DLP] Finished in {round(elapsed, 2)}s")

            if cancel_event.is_set():
                update_status(download_id, {"status": "cancelled"})
                return

            if not os.path.exists(video_path) and not audio_only:
                raise FileNotFoundError("Download succeeded but file not found.")

            if audio_only:
                update_status(download_id, {"status": "converting"})
                final_path = convert_to_mp3(video_path, audio_path)
                os.remove(video_path)
                file_url = f"{SERVER_URL}/audios/{os.path.basename(final_path)}"
                final_size = os.path.getsize(final_path)
            else:
                file_url = f"{SERVER_URL}/videos/{os.path.basename(video_path)}"
                final_size = os.path.getsize(video_path)

            update_status(download_id, {
                "status": "completed",
                "progress": 100,
                "speed": "0KB/s",
                "video_url": file_url
            })

            save_to_history({
                "id": download_id,
                "title": os.path.basename(file_url),
                "resolution": resolution or "audio",
                "status": "completed",
                "size": round(final_size / 1024 / 1024, 2)
            })

        except yt_dlp.utils.DownloadError as e:
            msg = str(e).lower()
            if "sign in" in msg or "captcha" in msg:
                error_msg = "🔐 Login or CAPTCHA required."
            elif "unsupported url" in msg:
                error_msg = "❌ Unsupported or invalid video link."
            else:
                error_msg = "❌ Download failed."
            print(f"[YT-DLP ERROR] {e}")
            update_status(download_id, {"status": "error", "error": error_msg})

        except Exception as e:
            print(f"[UNEXPECTED ERROR] {e}")
            traceback.print_exc()
            update_status(download_id, {"status": "error", "error": "❌ Unexpected error occurred."})

    thread = threading.Thread(target=run, daemon=True)
    _download_threads[download_id] = thread
    thread.start()
    return download_id


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
    # Not implemented yet
    return False


def resume_download(download_id):
    # Not implemented yet
    return False


def get_video_info(url, headers=None, download_id=None):
    return extract_metadata(url, headers=headers, download_id=download_id)
