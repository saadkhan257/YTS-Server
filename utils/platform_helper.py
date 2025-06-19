import os
import re

# === PLATFORM DETECTION ===

def detect_platform(url: str) -> str:
    """
    Detects the platform based on known patterns in the URL.
    """
    url = url.lower().strip()

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

COOKIE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'cookies'))

FILENAME_MAP = {
    'youtube': 'yt_cookies.txt',
    'facebook': 'fb_cookies.txt',
    'instagram': 'ig_cookies.txt',
    'tiktok': 'tt_cookies.txt',
    'x': 'x_cookies.txt',
    'threads': 'threads_cookies.txt',
}

def get_cookie_file_for_platform(platform: str) -> str | None:
    """
    Returns absolute cookie file path if it exists, else None.
    """
    fname = FILENAME_MAP.get(platform)
    if not fname:
        print(f"[COOKIES] ⚠️ No known cookie file mapping for platform: {platform}")
        return None

    path = os.path.join(COOKIE_DIR, fname)
    if os.path.exists(path) and os.path.isfile(path):
        print(f"[COOKIES] ✅ Using platform cookie file: {path}")
        return path
    else:
        print(f"[COOKIES] ❌ Cookie file missing: {path}")
        return None

def merge_headers_with_cookie(headers: dict, platform: str) -> dict:
    """
    Merges headers with cookie content from file (if available and not overridden).
    """
    merged = headers.copy() if headers else {}

    # If app already sent 'Cookie' header, we trust that (user-provided)
    if 'Cookie' in merged:
        print(f"[HEADERS] ⚠️ Using 'Cookie' from request headers — overriding local file.")
        return merged

    cookie_path = get_cookie_file_for_platform(platform)
    if cookie_path:
        try:
            with open(cookie_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    merged['Cookie'] = content
                    print(f"[COOKIES] 🧠 Injected cookie content into headers for: {platform}")
        except Exception as e:
            print(f"[COOKIES] ⚠️ Failed to read cookie file: {cookie_path} | Error: {e}")

    return merged
