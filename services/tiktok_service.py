import os
import time
import yt_dlp
import requests
import traceback
import uuid

from config import VIDEO_DIR, PROXY_URL
from utils.status_manager import update_status
from utils.history_manager import save_to_history
from utils.platform_helper import merge_headers_with_cookie, get_cookie_file_for_platform
from breakers.tt_protection_breaker import extract_with_fallbacks

DEFAULT_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    )
}

def resolve_redirect(url: str) -> str:
    try:
        proxies = {'http': PROXY_URL, 'https': PROXY_URL} if PROXY_URL else None
        res = requests.get(url, allow_redirects=True, timeout=10, headers=DEFAULT_HEADERS, proxies=proxies)
        return res.url
    except Exception as e:
        print(f"[TIKTOK] ⚠️ Redirect resolve error: {e}")
        return url

def fetch_tiktok_info(url: str, headers=None) -> dict:
    try:
        resolved_url = resolve_redirect(url)
        headers = merge_headers_with_cookie(headers or DEFAULT_HEADERS.copy(), "tiktok")

        info = extract_with_fallbacks(resolved_url, headers)
        formats = info.get("formats", [])
        resolutions, sizes, seen = [], [], set()
        duration = int(info.get("duration", 0))

        for f in formats:
            if f.get("ext") != "mp4" or not f.get("height"):
                continue
            label = f"{f['height']}p"
            if label in seen:
                continue
            seen.add(label)
            resolutions.append(label)
            size = f.get("filesize") or f.get("filesize_approx")
            sizes.append(f"{round(size / 1024 / 1024, 2)}MB" if size else "N/A")

        return {
            "title": info.get("title", "TikTok Video"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader", "TikTok"),
            "duration": duration,
            "video_url": resolved_url,
            "resolutions": resolutions,
            "sizes": sizes
        }

    except Exception as e:
        traceback.print_exc()
        return {"error": f"❌ TikTok info fetch failed: {e}"}

def download_tiktok(url: str, resolution: str, download_id: str, server_url: str, headers=None):
    try:
        resolved_url = resolve_redirect(url)
        headers = merge_headers_with_cookie(headers or DEFAULT_HEADERS.copy(), "tiktok")
        info = extract_with_fallbacks(resolved_url, headers)

        formats = info.get("formats", [])
        height = int(resolution.replace("p", ""))
        selected = None

        for f in formats:
            if f.get("ext") != "mp4" or not f.get("height"):
                continue
            if f["height"] == height:
                selected = f
                break

        if not selected and formats:
            selected = formats[0]

        if not selected or "url" not in selected:
            raise Exception("❌ Suitable video format not found")

        video_url = selected["url"]
        output_file = f"{download_id}.mp4"
        output_path = os.path.join(VIDEO_DIR, output_file)

        r = requests.get(video_url, stream=True, timeout=30)
        with open(output_path, "wb") as f:
            downloaded = 0
            total = int(r.headers.get("Content-Length", 0))
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    _progress_hook_manual(downloaded, total, download_id)

        if not os.path.exists(output_path):
            raise Exception("❌ File not found after download")

        update_status(download_id, {
            "status": "completed",
            "progress": 100,
            "speed": "0KB/s",
            "video_url": f"{server_url}/videos/{output_file}"
        })

        save_to_history({
            "id": download_id,
            "title": os.path.basename(output_file),
            "resolution": resolution,
            "status": "completed",
            "size": round(os.path.getsize(output_path) / 1024 / 1024, 2)
        })

    except Exception as e:
        print(f"[TIKTOK ERROR] ❌ {e}")
        update_status(download_id, {
            "status": "error",
            "progress": 0,
            "speed": "0KB/s",
            "error": str(e)
        })

def _progress_hook_manual(downloaded, total, download_id):
    percent = int((downloaded / total) * 100) if total else 0
    speed = "N/A"  # You can measure time deltas to calculate speed if needed
    update_status(download_id, {
        "status": "downloading",
        "progress": percent,
        "speed": speed
    })
