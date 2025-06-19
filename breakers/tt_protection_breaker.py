# breakers/tt_protection_breaker.py

import os
import re
import json
import time
import random
import requests
import tempfile
import traceback
import yt_dlp

from urllib.parse import urlparse
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from undetected_chromedriver import Chrome, ChromeOptions

GLOBAL_PROXY = os.getenv("YTS_PROXY")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

def breaker(func):
    def wrapper(url, headers=None):
        try:
            print(f"[BREAKER 🚀] Trying: {func.__name__}")
            return func(url, headers or DEFAULT_HEADERS)
        except Exception as e:
            print(f"[BREAKER ❌] Failed: {func.__name__} - {e}")
            traceback.print_exc()
            return None
    return wrapper


# -----------------------------------------------
# METHOD 1 — yt-dlp native
# -----------------------------------------------
@breaker
def method_yt_dlp(url, headers):
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'forcejson': True,
        'noplaylist': True,
        'http_headers': headers
    }
    if GLOBAL_PROXY:
        ydl_opts['proxy'] = GLOBAL_PROXY

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)


# -----------------------------------------------
# METHOD 2 — Selenium headless extraction
# -----------------------------------------------
@breaker
def method_selenium_headless(url, headers):
    options = ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument(f"user-agent={headers['User-Agent']}")
    options.add_argument('--no-sandbox')

    if GLOBAL_PROXY:
        options.add_argument(f'--proxy-server={GLOBAL_PROXY}')

    driver = Chrome(options=options)
    driver.get(url)

    time.sleep(5)

    video_elements = driver.find_elements(By.TAG_NAME, "video")
    video_url = None
    for video in video_elements:
        src = video.get_attribute("src")
        if src and src.startswith("http"):
            video_url = src
            break

    driver.quit()

    if not video_url:
        raise Exception("No video tag found in page")

    return {
        "webpage_url": url,
        "url": video_url,
        "title": "TikTok Video",
        "ext": "mp4",
        "formats": [{"format_id": "direct", "url": video_url, "ext": "mp4"}]
    }


# -----------------------------------------------
# METHOD 3 — Mobile redirect sniff
# -----------------------------------------------
@breaker
def method_mobile_redirect(url, headers):
    headers = headers.copy()
    headers["User-Agent"] = (
        "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/96.0.4664.45 Mobile Safari/537.36"
    )

    response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
    html = response.text
    match = re.search(r'"downloadAddr":"([^"]+)"', html)
    if not match:
        raise Exception("Video URL not found in mobile HTML")

    video_url = match.group(1).replace('\\u0026', '&').replace('\\', '')
    return {
        "webpage_url": url,
        "url": video_url,
        "title": "Mobile TikTok",
        "ext": "mp4",
        "formats": [{"format_id": "mobile", "url": video_url, "ext": "mp4"}]
    }


# -----------------------------------------------
# METHOD 4 — Clean TikTok watermark API (Unofficial)
# -----------------------------------------------
@breaker
def method_tikmate_api(url, headers):
    video_id = url.split("/")[-1].split("?")[0]
    api = f"https://api.tikmate.app/api/lookup?url=https://www.tiktok.com/@user/video/{video_id}"
    r = requests.get(api, headers=headers, timeout=10)
    data = r.json()
    if "token" not in data:
        raise Exception("Token not found from tikmate")

    dl_url = f"https://tikmate.app/download/{data['token']}/{video_id}.mp4"
    return {
        "webpage_url": url,
        "url": dl_url,
        "title": "No Watermark",
        "ext": "mp4",
        "formats": [{"format_id": "nowm", "url": dl_url, "ext": "mp4"}]
    }


# -----------------------------------------------
# METHOD 5 — Manual MP4 sniffing
# -----------------------------------------------
@breaker
def method_mp4_sniffing(url, headers):
    html = requests.get(url, headers=headers, timeout=10).text
    match = re.search(r'"contentUrl":"([^"]+)"', html)
    if not match:
        raise Exception("MP4 not found in HTML")
    return {
        "webpage_url": url,
        "url": match.group(1),
        "title": "Sniffed MP4",
        "ext": "mp4",
        "formats": [{"format_id": "sniffed", "url": match.group(1), "ext": "mp4"}]
    }


# -----------------------------------------------
# TRY ALL METHODS
# -----------------------------------------------
def extract_with_fallbacks(url, headers=None):
    methods = [
        method_yt_dlp,
        method_selenium_headless,
        method_mobile_redirect,
        method_tikmate_api,
        method_mp4_sniffing,
    ]

    for method in methods:
        info = method(url, headers)
        if info:
            print(f"[BREAKER ✅] {method.__name__} succeeded!")
            return info

    raise Exception("❌ All TikTok extraction methods failed.")
