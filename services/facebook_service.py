# 📁 services/facebook_service.py

import os
import requests
import yt_dlp

from config import VIDEO_DIR
from utils.status_manager import update_status
from utils.history_manager import save_to_history
from utils.platform_helper import load_cookies_from_file, merge_headers_with_cookie

# ✅ Default User-Agent
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    )
}

# ✅ Resolve redirect URLs (like fb.watch)
def resolve_facebook_redirect(url: str) -> str:
    try:
        res = requests.get(url, allow_redirects=True, timeout=10, headers=HEADERS)
        return res.url
    except Exception as e:
        print(f"[FB REDIRECT ERROR] {e}")
        return url

# ✅ Fetch Facebook metadata using yt-dlp (with fallback)
def fetch_facebook_info(url: str, request_headers: dict = None) -> dict:
    try:
        real_url = resolve_facebook_redirect(url)

        # 🧠 Combine headers
        cookies_txt = load_cookies_from_file("cookies/fb_cookies.txt")
        final_headers = merge_headers_with_cookie(HEADERS, cookies_txt, request_headers)

        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'forcejson': True,
            'http_headers': final_headers,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(real_url, download=False)

        formats = info.get("formats", [])
        seen = set()
        resolutions, sizes = [], []

        for f in formats:
            height = f.get("height")
            ext = f.get("ext", "")
            if not height or height > 1080 or ext != "mp4":
                continue

            label = f"{height}p"
            if label in seen:
                continue
            seen.add(label)

            filesize = f.get("filesize") or f.get("filesize_approx")
            if not filesize:
                bitrate = f.get("tbr") or 0
                duration = info.get("duration") or 0
                filesize = (bitrate * 1024 * duration) / 8 if bitrate and duration else 0

            sizes.append(f"{round(filesize / 1024 / 1024, 2)}MB" if filesize else "N/A")
            resolutions.append(label)

        duration_sec = int(info.get("duration") or 0)

        return {
            "platform": "Facebook",
            "title": info.get("title", "Untitled"),
            "thumbnail": info.get("thumbnail"),
            "resolutions": resolutions,
            "sizes": sizes,
            "duration": duration_sec,
            "uploader": info.get("uploader", "Facebook User"),
            "videoUrl": url
        }

    except Exception as e:
        print(f"[FB ERROR] Metadata fetch failed: {e}")
        return {"error": "❌ Could not fetch Facebook video info."}

# ✅ Facebook download using yt-dlp
def download_facebook(url: str, resolution: str, download_id: str, server_url: str, request_headers: dict = None):
    try:
        real_url = resolve_facebook_redirect(url)
        height = int(resolution.replace("p", ""))
        output_path = os.path.join(VIDEO_DIR, f"{download_id}.%(ext)s")

        # ✅ Load and merge cookies + headers
        cookies_txt = load_cookies_from_file("cookies/fb_cookies.txt")
        final_headers = merge_headers_with_cookie(HEADERS, cookies_txt, request_headers)

        ydl_opts = {
            'format': f"bestvideo[ext=mp4][height={height}]+bestaudio[ext=m4a]/best[ext=mp4][height={height}]/best",
            'outtmpl': output_path,
            'quiet': True,
            'http_headers': final_headers,
            'progress_hooks': [lambda d: _progress_hook(d, download_id)],
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegMerger',
                'preferredformat': 'mp4',
            }],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(real_url, download=True)

        final_file = f"{download_id}.mp4"
        final_path = os.path.join(VIDEO_DIR, final_file)

        if not os.path.exists(final_path):
            raise Exception("File not found after Facebook download.")

        update_status(download_id, {
            "status": "completed",
            "progress": 100,
            "speed": "0KB/s",
            "video_url": f"{server_url}/videos/{final_file}"
        })

        size_mb = round(os.path.getsize(final_path) / 1024 / 1024, 2)

        save_to_history({
            "id": download_id,
            "title": info.get("title", "Untitled Facebook Video"),
            "resolution": resolution,
            "status": "completed",
            "size": size_mb
        })

    except Exception as e:
        print(f"[FB ERROR] Download failed: {e}")
        update_status(download_id, {
            "status": "error",
            "progress": 0,
            "speed": "0KB/s",
            "error": str(e)
        })

# ✅ Progress tracker
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
