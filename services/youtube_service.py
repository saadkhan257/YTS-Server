import os
import threading
import uuid
import random
import string
import yt_dlp
import traceback
import tempfile

from config import VIDEO_DIR, AUDIO_DIR, SERVER_URL
from utils.platform_helper import (
    detect_platform,
    merge_headers_with_cookie,
    get_cookie_file_for_platform
)
from utils.status_manager import update_status
from utils.history_manager import save_to_history

GLOBAL_PROXY = os.getenv("YTS_PROXY")

LANGUAGE_MAP = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese",
    "hi": "Hindi", "ur": "Urdu", "ru": "Russian", "ja": "Japanese", "ko": "Korean",
    "tr": "Turkish", "ar": "Arabic", "id": "Indonesian", "it": "Italian", "pl": "Polish",
    "vi": "Vietnamese", "zh": "Chinese", "fa": "Persian", "bn": "Bengali"
}

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
    temp.write(cookie_str.strip())
    temp.close()
    return temp.name

def map_language_code(code):
    return LANGUAGE_MAP.get(code.lower(), code.upper())

# === METADATA EXTRACTOR ===

def get_video_info(url: str, headers: dict = None) -> dict:
    platform = detect_platform(url)
    merged_headers = merge_headers_with_cookie(headers or {}, platform)
    temp_cookie_path = None

    try:
        cookie_file = (
            write_temp_cookie_file(headers['Cookie'])
            if headers and 'Cookie' in headers
            else get_cookie_file_for_platform(platform)
        )

        ydl_opts = {
            'quiet': True,
            'noplaylist': True,
            'ignoreerrors': True,
            'cookiefile': cookie_file,
            'http_headers': merged_headers,
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',
            'forcejson': True,
            'dump_single_json': True
        }

        if GLOBAL_PROXY:
            ydl_opts['proxy'] = GLOBAL_PROXY

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            raise Exception("yt-dlp returned empty info")

        resolutions, audios, dubs = [], [], []
        seen_res, seen_aud, seen_dub_codes = set(), set(), set()
        duration = info.get("duration", 0)

        for f in info.get("formats", []):
            ext = f.get("ext")
            height = f.get("height")
            vcodec = f.get("vcodec")
            acodec = f.get("acodec")
            format_id = f.get("format_id")
            abr = f.get("abr")
            tbr = f.get("tbr")
            lang_code = f.get("language") or f.get("language_code")
            size_bytes = f.get("filesize") or f.get("filesize_approx")

            if not size_bytes and tbr and duration:
                try:
                    size_bytes = int(tbr * 1024 * duration / 8)
                except:
                    size_bytes = None

            size_str = human_readable_size(size_bytes)

            # 🎥 Video formats
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

            # 🎧 Audio formats
            if acodec != "none" and vcodec == "none" and ext in ("m4a", "webm"):
                if abr and abr not in seen_aud:
                    seen_aud.add(abr)
                    audios.append({
                        "label": f"{int(abr)}kbps",
                        "size": size_str,
                        "format_id": format_id
                    })

            # 🌐 Dubs
            if acodec != "none" and vcodec == "none" and lang_code:
                lang = lang_code.lower()
                if lang not in seen_dub_codes:
                    seen_dub_codes.add(lang)
                    dubs.append({
                        "label": map_language_code(lang),
                        "language_code": lang,
                        "format_id": format_id,
                        "size": size_str
                    })

        return {
            "platform": platform,
            "title": info.get("title", "Untitled"),
            "thumbnail": info.get("thumbnail", ""),
            "uploader": info.get("uploader") or info.get("channel") or "Unknown",
            "duration": duration,
            "video_url": url,
            "resolutions": sorted(resolutions, key=lambda r: int(r["label"].replace("p", ""))),
            "audios": audios,
            "audio_dubs": sorted(dubs, key=lambda d: d["label"])
        }

    except Exception as e:
        print(f"[❌ METADATA ERROR] {e}")
        traceback.print_exc()
        return {"error": "❌ Unable to fetch video information."}

    finally:
        if temp_cookie_path and os.path.exists(temp_cookie_path):
            os.remove(temp_cookie_path)

# === PUBLIC DOWNLOAD ENTRYPOINT ===

def download_youtube(url: str, format_id: str, is_audio=False, label="", headers: dict = None) -> str:
    filename = generate_filename()
    extension = 'mp3' if is_audio else 'mp4'
    selected_format = format_id or ('bestaudio' if is_audio else 'best')
    outdir = AUDIO_DIR if is_audio else VIDEO_DIR
    outurl = f"{SERVER_URL}/audios/{filename}.{extension}" if is_audio else f"{SERVER_URL}/videos/{filename}.{extension}"

    return _start_download(
        url=url,
        format_id=selected_format,
        output_filename=f"{filename}.{extension}",
        label=label,
        audio_only=is_audio,
        headers=headers,
        output_dir=outdir,
        file_url=outurl,
        file_type='audio' if is_audio else 'video'
    )

# === WORKER THREAD ===

def _start_download(url, format_id, output_filename, label, audio_only, headers, output_dir, file_url, file_type):
    download_id = str(uuid.uuid4())
    output_path = os.path.join(output_dir, output_filename)
    platform = detect_platform(url)
    merged_headers = merge_headers_with_cookie(headers or {}, platform)
    temp_cookie_path = None

    cookie_file = (
        write_temp_cookie_file(headers['Cookie']) if headers and 'Cookie' in headers
        else get_cookie_file_for_platform(platform)
    )

    def run():
        update_status(download_id, {
            "status": "starting",
            "progress": 0,
            "speed": "0KB/s",
            "video_url": None,
            "file_type": file_type
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

            if GLOBAL_PROXY:
                ydl_opts['proxy'] = GLOBAL_PROXY

            if audio_only:
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
                ydl_opts['merge_output_format'] = 'mp3'
            else:
                ydl_opts['merge_output_format'] = 'mp4'

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print(f"[⏬ START] {output_filename} (format: {format_id})")
                info = ydl.extract_info(url, download=True)

            if not os.path.exists(output_path):
                raise FileNotFoundError("❌ File not found after download.")

            update_status(download_id, {
                "status": "completed",
                "progress": 100,
                "speed": "0KB/s",
                "video_url": file_url,
                "file_type": file_type
            })

            save_to_history({
                "id": download_id,
                "title": info.get("title", "Untitled"),
                "resolution": label or format_id,
                "status": "completed",
                "size": round(os.path.getsize(output_path) / 1024 / 1024, 2),
                "is_audio": audio_only
            })

            print(f"[✅ COMPLETED] {output_filename}")

        except Exception as e:
            print(f"[❌ DOWNLOAD ERROR] {e}")
            traceback.print_exc()
            update_status(download_id, {
                "status": "error",
                "progress": 0,
                "speed": "0KB/s",
                "error": str(e),
                "file_type": file_type
            })

        finally:
            if temp_cookie_path and os.path.exists(temp_cookie_path):
                os.remove(temp_cookie_path)

    threading.Thread(target=run, daemon=True).start()
    return download_id

# === PROGRESS TRACKER ===

def _progress_hook(d, download_id):
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