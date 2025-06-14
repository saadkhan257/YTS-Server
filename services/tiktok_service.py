import os
import time
import yt_dlp
import requests
import traceback
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

from config import VIDEO_DIR, PROXY_URL
from utils.status_manager import update_status
from utils.history_manager import save_to_history
from utils.platform_helper import merge_headers_with_cookie, get_cookie_file_for_platform

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

def fetch_tiktok_video_url_selenium(tiktok_url: str) -> str | None:
    try:
        print(f"🚀 [Selenium] Opening TikTok: {tiktok_url}")
        options = uc.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-blink-features=AutomationControlled")

        if PROXY_URL:
            proxy_host = PROXY_URL.split("@")[-1].replace("http://", "")
            options.add_argument(f'--proxy-server=http://{proxy_host}')

        driver = uc.Chrome(options=options)
        driver.set_page_load_timeout(20)
        driver.get(tiktok_url)
        time.sleep(5)

        video_element = driver.find_element(By.TAG_NAME, "video")
        video_url = video_element.get_attribute("src")
        driver.quit()

        if not video_url:
            raise Exception("Video element found, but no URL inside.")
        print(f"✅ [Selenium] Video URL: {video_url}")
        return video_url

    except Exception as e:
        print(f"❌ [Selenium] Failed to fetch video: {e}")
        return None

def fetch_tiktok_info(url: str, headers=None) -> dict:
    try:
        resolved_url = resolve_redirect(url)
        headers = merge_headers_with_cookie(headers or DEFAULT_HEADERS.copy(), "tiktok")
        cookie_file = get_cookie_file_for_platform("tiktok")

        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'forcejson': True,
            'http_headers': headers,
            'socket_timeout': 15,
            'retries': 3
        }

        if cookie_file:
            ydl_opts['cookiefile'] = cookie_file
        if PROXY_URL:
            ydl_opts['proxy'] = PROXY_URL

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(resolved_url, download=False)

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
                "title": info.get("title", "Untitled TikTok"),
                "thumbnail": info.get("thumbnail"),
                "uploader": info.get("uploader", "TikTok"),
                "duration": duration,
                "video_url": resolved_url,
                "resolutions": resolutions,
                "sizes": sizes
            }

        except Exception as e:
            print(f"[YTDLP ERROR] {e} — fallback to Selenium")

            selenium_url = fetch_tiktok_video_url_selenium(resolved_url)
            if selenium_url:
                return {
                    "title": "TikTok Video",
                    "thumbnail": None,
                    "uploader": "TikTok",
                    "duration": 0,
                    "video_url": selenium_url,
                    "resolutions": ["720p"],
                    "sizes": ["N/A"]
                }

            raise Exception("yt-dlp and Selenium both failed.")

    except Exception as e:
        traceback.print_exc()
        return {"error": f"❌ TikTok info fetch failed: {e}"}

def download_tiktok(url: str, resolution: str, download_id: str, server_url: str, headers=None):
    try:
        resolved_url = resolve_redirect(url)
        height = resolution.replace("p", "")
        output_file = f"{download_id}.mp4"
        output_path = os.path.join(VIDEO_DIR, output_file)

        headers = merge_headers_with_cookie(headers or DEFAULT_HEADERS.copy(), "tiktok")
        cookie_file = get_cookie_file_for_platform("tiktok")

        format_selector = f"bestvideo[height={height}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"

        ydl_opts = {
            'format': format_selector,
            'outtmpl': output_path,
            'quiet': True,
            'noplaylist': True,
            'merge_output_format': 'mp4',
            'http_headers': headers,
            'progress_hooks': [lambda d: _progress_hook(d, download_id)],
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4'
            }],
            'socket_timeout': 15,
            'retries': 3
        }

        if cookie_file:
            ydl_opts['cookiefile'] = cookie_file
        if PROXY_URL:
            ydl_opts['proxy'] = PROXY_URL

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.download([resolved_url])

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

def _progress_hook(d, download_id):
    if d['status'] != 'downloading':
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
