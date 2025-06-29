import os
from datetime import timedelta
from dotenv import load_dotenv

# ✅ Load .env if present
load_dotenv()

# ✅ Base Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_DIR = os.path.join(BASE_DIR, "static", "videos")
AUDIO_DIR = os.path.join(BASE_DIR, "static", "audios")
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# ✅ Server Configuration
USE_EXTERNAL_DOMAIN = os.getenv("USE_EXTERNAL_DOMAIN", "true").lower() == "true"
EXTERNAL_DOMAIN = os.getenv("EXTERNAL_DOMAIN", "yts-server.technicalforest.com")
SCHEME = os.getenv("SCHEME", "https")  # "http" or "https"

# ✅ Local Dev Fallback
SERVER_HOST = os.getenv("SERVER_HOST", "134.209.155.111")
SERVER_PORT = int(os.getenv("SERVER_PORT", "5000"))

# ✅ Final URL Builder
if USE_EXTERNAL_DOMAIN:
    SERVER_URL = f"{SCHEME}://{EXTERNAL_DOMAIN}"
else:
    SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

# ✅ Media Expiration
DELETE_OLDER_THAN = timedelta(
    minutes=int(os.getenv("DELETE_AFTER_MINUTES", "15"))
)

# ✅ Supported Platforms
SUPPORTED_PLATFORMS = {
    "youtube": ["youtube.com", "youtu.be"],
    "tiktok": ["tiktok.com", "vt.tiktok.com", "vm.tiktok.com"],
    "facebook": ["facebook.com", "fb.watch"],
    "instagram": ["instagram.com"]
}

# ✅ TikTok Cookie Support
TIKTOK_COOKIES_FILE = os.path.join(BASE_DIR, "tt_cookies.txt")
ENABLE_TIKTOK_COOKIES = os.getenv("ENABLE_TIKTOK_COOKIES", "true").lower() == "true"

# ✅ Debug Flags
ENABLE_LOGGING = os.getenv("ENABLE_LOGGING", "true").lower() == "true"
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# ✅ History File Path
HISTORY_FILE = os.path.join(BASE_DIR, "utils", "history.json")
