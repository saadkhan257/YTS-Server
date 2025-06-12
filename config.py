# 📁 config.py

import os
from datetime import timedelta
from dotenv import load_dotenv

# ✅ Load .env variables if present
load_dotenv()

# ✅ Base Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_DIR = os.path.join(BASE_DIR, "static", "videos")
os.makedirs(VIDEO_DIR, exist_ok=True)

# ✅ Flask Bind Config (Local)
SERVER_HOST: str = os.getenv("SERVER_HOST", "134.209.155.111")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "5000"))

# ✅ Internal-only server URL (used in downloader to generate file links)
SERVER_URL: str = f"http://{SERVER_HOST}:{SERVER_PORT}"

# ✅ Auto-clean media older than X minutes
DELETE_OLDER_THAN: timedelta = timedelta(
    minutes=int(os.getenv("DELETE_AFTER_MINUTES", "15"))
)

# ✅ Supported Platforms
SUPPORTED_PLATFORMS: dict = {
    "youtube": ["youtube.com", "youtu.be"],
    "tiktok": ["tiktok.com", "vt.tiktok.com", "vm.tiktok.com"],
    "facebook": ["facebook.com", "fb.watch"],
    "instagram": ["instagram.com"]
}

# ✅ TikTok Cookie Configuration
TIKTOK_COOKIES_FILE: str = os.path.join(BASE_DIR, "tt_cookies.txt")
ENABLE_TIKTOK_COOKIES: bool = os.getenv("ENABLE_TIKTOK_COOKIES", "true").lower() == "true"

# ✅ Logging + Debugging Flags
ENABLE_LOGGING: bool = os.getenv("ENABLE_LOGGING", "true").lower() == "true"
DEBUG_MODE: bool = os.getenv("DEBUG_MODE", "false").lower() == "true"

# ✅ Local Download History File
HISTORY_FILE: str = os.path.join(BASE_DIR, "utils", "history.json")