# 📂 instagram_service.py

import yt_dlp
import os
from config import VIDEO_DIR
from utils.status_manager import update_status
from utils.history_manager import save_to_history

# ✅ Default headers
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    )
}

# ✅ Load cookies/ig_cookies.txt if available
COOKIE_FILE = "cookies/ig_cookies.txt"
USE_COOKIES = os.path.exists(COOKIE_FILE)


def fetch_instagram_info(url: str) -> dict:
    try:
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'forcejson': True,
            'http_headers': HEADERS,
            'extract_flat': False,
        }

        if USE_COOKIES:
            ydl_opts['cookiefile'] = COOKIE_FILE

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if "entries" in info:
            info = info["entries"][0]

        formats = info.get("formats", [])
        seen = set()
        resolutions = []
        sizes = []

        for f in formats:
            ext = f.get("ext")
            height = f.get("height")
            vcodec = f.get("vcodec") or ""
            acodec = f.get("acodec") or ""

            if not height or ext != "mp4" or vcodec == "none" or acodec == "none":
                continue

            if height > 1080:
                continue

            label = f"{height}p"
            if label in seen:
                continue
            seen.add(label)

            # ✅ Accurate filesize calculation
            filesize = f.get("filesize") or f.get("filesize_approx")
            if not filesize:
                bitrate = f.get("tbr") or 0
                duration = info.get("duration") or 0
                filesize = (bitrate * 1024 * duration) / 8 if bitrate and duration else 0

            sizes.append(f"{round(filesize / 1024 / 1024, 2)}MB" if filesize else "N/A")
            resolutions.append(label)

        # ✅ Accurate duration fallback
        duration_sec = int(info.get("duration") or 0)
        if not duration_sec:
            duration_sec = int(formats[0].get("duration", 0)) if formats else 0

        return {
            "platform": "Instagram",
            "title": info.get("title", "Untitled"),
            "thumbnail": info.get("thumbnail"),
            "resolutions": resolutions,
            "sizes": sizes,
            "duration": duration_sec,
            "uploader": info.get("uploader", "Instagram User"),
            "videoUrl": url
        }

    except Exception as e:
        print(f"[IG ERROR] Metadata failed: {e}")
        return {"error": "❌ Could not fetch Instagram info."}


def download_instagram(url: str, resolution: str, download_id: str, server_url: str):
    try:
        height = int(resolution.replace("p", ""))
        output_path = os.path.join(VIDEO_DIR, f"{download_id}.%(ext)s")

        format_selector = (
            f"bestvideo[ext=mp4][height={height}]+bestaudio[ext=m4a]/"
            f"best[ext=mp4][height={height}]/best"
        )

        ydl_opts = {
            'format': format_selector,
            'outtmpl': output_path,
            'quiet': True,
            'http_headers': HEADERS,
            'progress_hooks': [lambda d: _progress_hook(d, download_id)],
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegMerger',
                'preferredformat': 'mp4',
            }],
        }

        if USE_COOKIES:
            ydl_opts['cookiefile'] = COOKIE_FILE

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        final_file = f"{download_id}.mp4"
        final_path = os.path.join(VIDEO_DIR, final_file)

        if not os.path.exists(final_path):
            raise Exception("❌ File not found after Instagram download.")

        update_status(download_id, {
            "status": "completed",
            "progress": 100,
            "speed": "0KB/s",
            "video_url": f"{server_url}/videos/{final_file}"
        })

        size_mb = round(os.path.getsize(final_path) / 1024 / 1024, 2)

        save_to_history({
            "id": download_id,
            "title": info.get("title", "Untitled Instagram Video"),
            "resolution": resolution,
            "status": "completed",
            "size": size_mb
        })

    except Exception as e:
        print(f"[IG ERROR] Download failed: {e}")
        update_status(download_id, {
            "status": "error",
            "progress": 0,
            "speed": "0KB/s",
            "error": str(e)
        })


def _progress_hook(d, download_id):
    if d['status'] == 'downloading':
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
