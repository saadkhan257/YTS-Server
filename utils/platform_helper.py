import os
import re

# === PLATFORM DETECTION ===

def detect_platform(url: str) -> str:
    """
    Detects the platform based on known patterns in the URL.
    """
    url = url.lower()

    platform_patterns = {
        'youtube': r'(youtube\.com|youtu\.be)',
        'facebook': r'(facebook\.com|fb\.watch)',
        'instagram': r'(instagram\.com|instagr\.am)',
        'tiktok': r'(tiktok\.com)',
        'twitter': r'(twitter\.com|x\.com)',
        'threads': r'(threads\.net)',
    }

    for platform, pattern in platform_patterns.items():
        if re.search(pattern, url):
            return platform

    return 'unknown'

# === COOKIE HANDLING ===

def get_cookie_file_for_platform(platform: str) -> str:
    """
    Returns the cookie file path for a given platform.
    """
    filename_map = {
        'youtube': 'yt_cookies.txt',
        'facebook': 'fb_cookies.txt',
        'instagram': 'ig_cookies.txt',
        'tiktok': 'tt_cookies.txt',
        'twitter': 'tw_cookies.txt',
        'threads': 'threads_cookies.txt'
    }

    fname = filename_map.get(platform)
    if not fname:
        return ""

    cookie_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'cookies', fname))
    return cookie_path if os.path.exists(cookie_path) else ""

def merge_headers_with_cookie(headers: dict, platform: str) -> dict:
    """
    Merges headers with platform cookie content if provided.
    Cookie in headers will override local file.
    """
    merged = headers.copy() if headers else {}

    # If cookie header is already provided by frontend (from in-app webview), use it
    if 'Cookie' in merged:
        return merged

    cookie_file = get_cookie_file_for_platform(platform)
    if cookie_file and os.path.exists(cookie_file):
        try:
            with open(cookie_file, 'r', encoding='utf-8') as f:
                cookie_text = f.read().strip()
                if cookie_text:
                    merged['Cookie'] = cookie_text
        except Exception as e:
            print(f"[⚠️ Cookie Read Error] {e}")

    return merged
