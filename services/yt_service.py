import os
import uuid
import yt_dlp
import tempfile
import traceback
import random
import string
import threading
from time import sleep

from config import VIDEO_DIR, SERVER_URL
from utils.platform_helper import merge_headers_with_cookie, get_cookie_file_for_platform
from utils.status_manager import update_status
from utils.history_manager import save_to_history
from utils.download_registry import register_thread, register_cancel_event

# --- Constants and Setup ---
AUDIO_DIR = os.path.join("static", "audios")
os.makedirs(AUDIO_DIR, exist_ok=True)

SUPPORTED_AUDIO_FORMATS = {"m4a", "mp3", "aac", "opus"}
MP4_EXTENSIONS = {"mp4", "m4v", "mov"}
GLOBAL_PROXY = os.getenv("YTS_PROXY")
TEMP_COOKIE_SUFFIX = "_cookie.txt"

_download_threads = {}
_download_locks = {}

def generate_filename(prefix="YTSx"):
    token = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
    return f"{prefix}_{token}"

def _prepare_cookie_file(headers, platform):
    if headers and headers.get("Cookie"):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=TEMP_COOKIE_SUFFIX, mode='w')
        tmp.write(headers["Cookie"])
        tmp.close()
        print(f"[COOKIES] 🧠 Using temp cookie file: {tmp.name}")
        return tmp.name
    return get_cookie_file_for_platform(platform)

def _progress_hook(d, download_id, cancel_event):
    if cancel_event.is_set():
        raise Exception("Cancelled by user")
    if d.get("status") == "downloading":
        t = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
        done = d.get("downloaded_bytes", 0)
        pct = int((done / t) * 100)
        speed = d.get("speed", 0)
        speed_str = f"{round(speed / 1024,1)}KB/s" if speed else "0KB/s"
        update_status(download_id, {"status": "downloading", "progress": pct, "speed": speed_str})

def _normalize_url(url: str):
    if "/shorts/" in url:
        return url.replace("/shorts/", "/watch?v=")
    return url

# --- Metadata Extraction ---
def extract_yt_metadata(url, headers=None, download_id=None):
    import collections

    download_id = download_id or str(uuid.uuid4())
    cancel_event = threading.Event()
    _download_locks[download_id] = cancel_event
    update_status(download_id, {"status": "extracting", "progress": 0, "speed": "0KB/s"})

    url = _normalize_url(url)
    merged_headers = merge_headers_with_cookie(headers or {}, "youtube")
    cookie_file = _prepare_cookie_file(headers or {}, "youtube")

    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'forcejson': True,
        'noplaylist': True,
        'http_headers': merged_headers,
        'cookiefile': cookie_file,
        'proxy': GLOBAL_PROXY,
        'progress_hooks': [lambda d: _progress_hook(d, download_id, cancel_event)],
        'user_agent': 'Mozilla/5.0 (X11; Linux x86_64)',
        'nocheckcertificate': True,
        'retries': 3,
        'retry_sleep': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = info.get("formats", [])
        duration = info.get("duration") or 0

        resolutions = []
        resolution_map = collections.OrderedDict()
        audio_formats = collections.OrderedDict()
        audio_dubs = collections.OrderedDict()

        for fmt in formats:
            ext = fmt.get("ext")
            vcodec = fmt.get("vcodec")
            acodec = fmt.get("acodec")
            abr = fmt.get("abr")
            height = fmt.get("height")
            lang = fmt.get("language") or fmt.get("language_code")
            fmt_id = fmt.get("format_id")
            tbr = fmt.get("tbr")

            filesize = fmt.get("filesize") or fmt.get("filesize_approx") or 0
            if not filesize and tbr:
                filesize = (tbr * 1000 / 8) * duration  # estimate in bytes

            size_str = f"{round(filesize / 1024 / 1024, 2)}MB" if filesize else "Unknown"

            # --- AUDIO FORMAT ---
            if vcodec == "none" and acodec and abr and ext in SUPPORTED_AUDIO_FORMATS:
                label = f"{int(abr)}K"
                if label not in audio_formats:
                    audio_formats[label] = {
                        "label": label,
                        "abr": abr,
                        "ext": ext,
                        "acodec": acodec,
                        "format_id": fmt_id,
                        "size": size_str
                    }

            # --- AUDIO DUBS ---
            if lang and vcodec == "none":
                lang_code = lang.lower()
                if lang_code not in audio_dubs:
                    audio_dubs[lang_code] = {
                        "lang": lang_code,
                        "label": lang.upper(),
                        "format_id": fmt_id,
                        "ext": ext,
                        "acodec": acodec
                    }

            # --- VIDEO FORMAT ---
            if height and vcodec and ext in MP4_EXTENSIONS:
                label = f"{height}p"
                if label not in resolution_map:
                    resolution_map[label] = {
                        "height": height,
                        "ext": ext,
                        "vcodec": vcodec,
                        "format_id": fmt_id,
                        "size": size_str
                    }

        resolutions = list(resolution_map.keys())
        sizes = [v["size"] for v in resolution_map.values()]
        audio_format_list = list(audio_formats.values())
        audio_dub_list = list(audio_dubs.values())

        # --- Optional: subtitles (for future expansion) ---
        # subtitles = info.get("subtitles", {})
        # subtitle_langs = list(subtitles.keys())

        update_status(download_id, {"status": "ready", "progress": 0})

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
            "videoFormats": list(resolution_map.values()),
            "audioFormats": audio_format_list,
            "audio_dubs": audio_dub_list,
            # "subtitles": subtitle_langs,
        }

    except Exception as e:
        traceback.print_exc()
        msg = str(e)[:200]
        update_status(download_id, {"status": "error", "error": msg})
        return {"error": msg, "download_id": download_id}

# --- Audio Download ---
def start_yt_audio_download(url, headers=None, audio_quality="192"):
    download_id = str(uuid.uuid4())
    filename = generate_filename("yt_audio")
    output = os.path.join(AUDIO_DIR, f"{filename}.mp3")
    cancel_event = threading.Event()
    _download_locks[download_id] = cancel_event

    def _run():
        update_status(download_id, {"status": "starting", "progress": 0})
        merged_headers = merge_headers_with_cookie(headers or {}, "youtube")
        cookie_file = _prepare_cookie_file(headers or {}, "youtube")

        ydl_opts = {
            # Strictly match abr (audio bitrate)
            'format': f"bestaudio[abr={audio_quality}][ext=mp3]/bestaudio[abr={audio_quality}]/bestaudio",
            'outtmpl': output,
            'quiet': True,
            'noplaylist': True,
            'http_headers': merged_headers,
            'cookiefile': cookie_file,
            'proxy': GLOBAL_PROXY,
            'progress_hooks': [lambda d: _progress_hook(d, download_id, cancel_event)],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': audio_quality
            }],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            if cancel_event.is_set():
                update_status(download_id, {"status": "cancelled"})
                return
            update_status(download_id, {
                "status": "completed",
                "audio_url": f"{SERVER_URL}/audios/{os.path.basename(output)}"
            })
            save_to_history({
                "id": download_id,
                "title": os.path.basename(output),
                "resolution": f"{audio_quality}K",
                "status": "completed",
                "size": round(os.path.getsize(output)/1024/1024, 2)
            })
        except Exception as e:
            traceback.print_exc()
            msg = str(e)[:200]
            update_status(download_id, {"status": "error", "error": msg})

    th = threading.Thread(target=_run, daemon=True)
    register_thread(download_id, th)
    th.start()
    return download_id


# --- Video Download ---
def start_yt_video_download(url, resolution, headers=None, audio_lang=None, bandwidth_limit=None):
    download_id = str(uuid.uuid4())
    filename = generate_filename("yt_vid")
    output = os.path.join(VIDEO_DIR, f"{filename}.mp4")
    cancel_event = threading.Event()
    _download_locks[download_id] = cancel_event
    register_cancel_event(download_id, cancel_event)

    def _parse_rl(lim):
        try:
            if isinstance(lim, (int, float)): return lim * 1024
            s = str(lim).strip().upper()
            unit = s[-1]; val = float(s[:-1])
            return val * {"K":1e3, "M":1e6, "G":1e9}.get(unit, 1)
        except:
            return None

    def _run():
        update_status(download_id, {"status": "starting", "progress": 0})
        merged_headers = merge_headers_with_cookie(headers or {}, "youtube")
        cookie_file = _prepare_cookie_file(headers or {}, "youtube")
        res = resolution.replace("p", "")

        # Prioritize video of given resolution
        video_fmt = f"bestvideo[height={res}][ext=mp4]"

        # Prioritize dub audio if given
        audio_fmt = "bestaudio[ext=m4a]"
        if audio_lang:
            audio_fmt = f"bestaudio[language={audio_lang}][ext=m4a]/bestaudio[ext=m4a]"

        opts = {
            'format': f"{video_fmt}+{audio_fmt}/best",
            'outtmpl': output,
            'quiet': True,
            'noplaylist': True,
            'http_headers': merged_headers,
            'cookiefile': cookie_file,
            'proxy': GLOBAL_PROXY,
            'progress_hooks': [lambda d: _progress_hook(d, download_id, cancel_event)],
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4'
            }]
        }

        rl = _parse_rl(bandwidth_limit)
        if rl:
            opts['ratelimit'] = rl

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([_normalize_url(url)])
            if cancel_event.is_set():
                update_status(download_id, {"status": "cancelled"})
                return
            update_status(download_id, {
                "status": "completed",
                "video_url": f"{SERVER_URL}/videos/{os.path.basename(output)}"
            })
            save_to_history({
                "id": download_id,
                "title": os.path.basename(output),
                "resolution": resolution,
                "status": "completed",
                "size": round(os.path.getsize(output)/1024/1024, 2)
            })
        except Exception as e:
            traceback.print_exc()
            msg = str(e)[:200]
            update_status(download_id, {"status": "error", "error": msg})

    th = threading.Thread(target=_run, daemon=True)
    register_thread(download_id, th)
    th.start()
    return download_id
