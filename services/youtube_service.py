import os
import threading
import uuid
import random
import string
import yt_dlp
import traceback
import tempfile

from config import VIDEO_DIR, SERVER_URL
from utils.platform_helper import detect_platform, get_cookie_file_for_platform, merge_headers_with_cookie
from utils.status_manager import update_status
from utils.history_manager import save_to_history

# === GLOBALS ===
GLOBAL_PROXY = os.getenv("YTS_PROXY")

# === UTILS ===

def generate_filename():
    return f"YTSx_{''.join(random.choices(string.ascii_lowercase + string.digits, k=12))}"

def human_readable_size(size_bytes):
    if not size_bytes:
        return "Unknown"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"

def write_temp_cookie_file(cookie_str):
    temp = tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt')
    temp.write(cookie_str)
    temp.close()
    return temp.name

# === METADATA FETCHING ===

def get_video_info(url: str, headers: dict = None) -> dict:
    platform = detect_platform(url)
    merged_headers = merge_headers_with_cookie(headers or {}, platform)

    if 'Cookie' in (headers or {}):
        cookie_file = write_temp_cookie_file(headers['Cookie'])
    else:
        cookie_file = get_cookie_file_for_platform(platform)

    ydl_opts = {
        'quiet': True,
        'noplaylist': True,
        'ignoreerrors': True,
        'cookiefile': cookie_file,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'http_headers': merged_headers
    }

    if GLOBAL_PROXY:
        ydl_opts['proxy'] = GLOBAL_PROXY

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"[❌ METADATA ERROR] {e}")
        return {"error": "❌ Unable to fetch video information."}

    try:
        resolutions, audios = [], []
        seen_res, seen_aud = set(), set()
        duration = info.get("duration", 0)

        for f in info.get("formats", []):
            ext = f.get("ext")
            height = f.get("height")
            vcodec = f.get("vcodec")
            acodec = f.get("acodec")
            format_id = f.get("format_id")
            abr = f.get("abr")
            tbr = f.get("tbr")

            size_bytes = f.get("filesize") or f.get("filesize_approx")
            if not size_bytes and tbr and duration:
                try:
                    size_bytes = int(tbr * 1024 * duration / 8)
                except:
                    size_bytes = None
            size_str = human_readable_size(size_bytes)

            if height and vcodec != "none" and ext == "mp4":
                label = f"{height}p"
                if label not in seen_res:
                    seen_res.add(label)
                    resolutions.append({
                        "label": label,
                        "size": size_str,
                        "format_id": format_id,
                        "height": height
                    })

            elif acodec != "none" and vcodec == "none" and ext in ("m4a", "webm"):
                if abr and abr not in seen_aud:
                    seen_aud.add(abr)
                    audios.append({
                        "label": f"{int(abr)}kbps",
                        "size": size_str,
                        "format_id": format_id
                    })

        return {
            "platform": platform,
            "title": info.get("title", "Untitled"),
            "thumbnail": info.get("thumbnail", ""),
            "uploader": info.get("uploader", "Unknown"),
            "duration": duration,
            "video_url": url,
            "resolutions": sorted(resolutions, key=lambda r: int(r["label"].replace("p", ""))),
            "audios": audios
        }

    except Exception as e:
        print(f"[❌ FORMAT PARSING ERROR] {e}")
        traceback.print_exc()
        return {"error": "❌ Unable to parse available formats."}

# === DOWNLOAD DISPATCHER ===

def download_youtube(url: str, format_id: str, is_audio=False, label="", headers: dict = None) -> str:
    filename = generate_filename()
    extension = 'mp3' if is_audio else 'mp4'
    selected_format = format_id or ('bestaudio' if is_audio else 'best')

    return _start_download(
        url=url,
        format_id=selected_format,
        output_filename=f"{filename}.{extension}",
        label=label,
        audio_only=is_audio,
        headers=headers
    )

# === WORKER FUNCTION ===

def _start_download(url, format_id, output_filename, label, audio_only=False, headers=None) -> str:
    download_id = str(uuid.uuid4())
    output_path = os.path.join(VIDEO_DIR, output_filename)
    platform = detect_platform(url)
    merged_headers = merge_headers_with_cookie(headers or {}, platform)

    if 'Cookie' in (headers or {}):
        cookie_file = write_temp_cookie_file(headers['Cookie'])
    else:
        cookie_file = get_cookie_file_for_platform(platform)

    def run():
        update_status(download_id, {
            "status": "starting",
            "progress": 0,
            "speed": "0KB/s",
            "video_url": None
        })

        try:
            ydl_opts = {
                'format': format_id,
                'outtmpl': output_path,
                'quiet': True,
                'noplaylist': True,
                'cookiefile': cookie_file,
                'http_headers': merged_headers,
                'progress_hooks': [lambda d: _progress_hook(d, download_id)]
            }

            if audio_only:
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
                ydl_opts['merge_output_format'] = 'mp3'
            else:
                ydl_opts['merge_output_format'] = 'mp4'

            if GLOBAL_PROXY:
                ydl_opts['proxy'] = GLOBAL_PROXY

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print(f"[⏬ START] {output_filename} (format: {format_id})")
                info = ydl.extract_info(url, download=True)

            if not os.path.exists(output_path):
                raise FileNotFoundError("❌ Final file missing after download.")

            update_status(download_id, {
                "status": "completed",
                "progress": 100,
                "speed": "0KB/s",
                "video_url": f"{SERVER_URL}/videos/{output_filename}"
            })

            save_to_history({
                "id": download_id,
                "title": info.get("title", "Untitled"),
                "resolution": label or format_id,
                "status": "completed",
                "size": round(os.path.getsize(output_path) / 1024 / 1024, 2)
            })

            print(f"[✅ COMPLETED] {output_filename}")

        except Exception as e:
            print(f"[❌ DOWNLOAD ERROR] {e}")
            traceback.print_exc()
            update_status(download_id, {
                "status": "error",
                "progress": 0,
                "speed": "0KB/s",
                "error": str(e)
            })

    threading.Thread(target=run, daemon=True).start()
    return download_id

# === PROGRESS TRACKING ===

def _progress_hook(d, download_id):
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
