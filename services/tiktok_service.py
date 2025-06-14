# services/tiktok_service.py

import os
import time
import yt_dlp
import requests
import traceback

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from config import VIDEO_DIR
from utils.status_manager import update_status
from utils.history_manager import save_to_history
from utils.platform_helper import merge_headers_with_cookie
from breakers.tt_protection_breaker import extract_with_fallbacks

DEFAULT_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    )
}


def extract_info_with_selenium(url, headers=None):
    print(f"[TT_FALLBACK] Extracting with Selenium: {url}")

    options = Options()
    options.headless = True
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/117.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(options=options)
    driver.get(url)

    time.sleep(5)  # Give time for video to load

    video_elements = driver.find_elements("tag name", "video")
    video_url = video_elements[0].get_attribute("src") if video_elements else None

    driver.quit()

    if not video_url:
        raise Exception("❌ Failed to extract video URL from TikTok page.")

    return {
        "title": "TikTok Video",
        "formats": [{
            "ext": "mp4",
            "height": 720,
            "url": video_url
        }],
        "thumbnail": None,
        "uploader": "TikTok",
        "duration": None,
        "webpage_url": url
    }


def resolve_redirect(url: str) -> str:
    try:
        res = requests.get(url, allow_redirects=True, timeout=10, headers=DEFAULT_HEADERS)
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
    speed = "N/A"
    update_status(download_id, {
        "status": "downloading",
        "progress": percent,
        "speed": speed
    })
