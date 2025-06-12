# 📁 utils/platform_helper.py

import os
from urllib.parse import urlparse
from config import SUPPORTED_PLATFORMS

COOKIES_DIR = "cookies"

def detect_platform(url: str) -> str:
    """
    Detects the platform based on the input URL.
    Returns: 'youtube', 'tiktok', 'facebook', 'instagram', or 'unknown'
    """
    if not url or "http" not in url:
        return "unknown"

    try:
        domain = urlparse(url.lower()).netloc

        for platform, domains in SUPPORTED_PLATFORMS.items():
            if domain in domains or any(domain.endswith(f".{d}") for d in domains):
                return platform

    except Exception as e:
        print(f"[PLATFORM DETECTION ERROR] {e}")

    return "unknown"

def load_cookies_from_file(path: str) -> str:
    """
    Reads raw cookie string from a .txt file.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""

def get_default_cookies(platform: str) -> str:
    """
    Loads the default cookies for a platform from /cookies/<platform>_cookies.txt
    """
    cookie_path = os.path.join(COOKIES_DIR, f"{platform}_cookies.txt")
    return load_cookies_from_file(cookie_path)

def merge_headers_with_cookie(base_headers: dict, cookie_txt: str, override_headers: dict = None) -> dict:
    """
    Merge headers with cookie. Headers from override_headers take priority.
    """
    headers = base_headers.copy()
    if override_headers:
        headers.update(override_headers)
    if cookie_txt:
        headers["Cookie"] = cookie_txt
    return headers

def build_platform_headers(platform: str, base_headers: dict = None, override_headers: dict = None) -> dict:
    """
    Constructs headers for a given platform, merging base and user overrides with default cookies.
    """
    base_headers = base_headers or {}
    default_cookies = get_default_cookies(platform)
    return merge_headers_with_cookie(base_headers, default_cookies, override_headers)
