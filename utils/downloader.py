import os
import uuid
import threading
import traceback

from config import VIDEO_DIR, AUDIO_DIR, SERVER_URL
from utils.platform_helper import detect_platform
from utils.status_manager import update_status

# Platform service imports
from services.yt_service import (
    extract_yt_metadata, start_yt_audio_download, start_yt_video_download
)
from services.tt_service import (
    extract_tt_metadata, start_tt_audio_download, start_tt_video_download
)
from services.fb_service import (
    extract_fb_metadata, start_fb_audio_download, start_fb_video_download
)
from services.x_service import (
    extract_x_metadata, start_x_audio_download, start_x_video_download
)
from services.ig_service import (
    extract_ig_metadata, start_ig_audio_download, start_ig_video_download
)

# Internal state tracking
_download_threads = {}
_download_locks = {}

# Service dispatcher
SERVICE_MAP = {
    "youtube":   { "meta": extract_yt_metadata, "audio": start_yt_audio_download, "video": start_yt_video_download },
    "tiktok":    { "meta": extract_tt_metadata, "audio": start_tt_audio_download, "video": start_tt_video_download },
    "facebook":  { "meta": extract_fb_metadata, "audio": start_fb_audio_download, "video": start_fb_video_download },
    "x":         { "meta": extract_x_metadata,  "audio": start_x_audio_download,  "video": start_x_video_download },
    "instagram": { "meta": extract_ig_metadata, "audio": start_ig_audio_download, "video": start_ig_video_download }
}

# --- Main API Functions ---

def get_video_info(url, headers=None, download_id=None):
    download_id = str(download_id or uuid.uuid4())
    platform = detect_platform(url)

    print(f"\n[🔍 FETCH INFO]")
    print(f"🔗 URL: {url}")
    print(f"🛰️ Platform: {platform}")
    print(f"🆔 Download ID: {download_id}")

    if headers:
        has_cookie = any("cookie" in k.lower() for k in headers)
        print(f"📦 Headers received | Cookie present: {'✅' if has_cookie else '❌'}")
    else:
        print("📭 No headers received")

    service = SERVICE_MAP.get(platform)
    if not service or "meta" not in service:
        error = f"❌ Unsupported platform: {platform}"
        print(f"🚫 {error}")
        update_status(download_id, { "status": "error", "error": error })
        return { "error": error, "download_id": download_id }

    try:
        print(f"🧩 Executing: {platform}.extract_metadata()")
        result = service["meta"](url, headers=headers, download_id=download_id)

        if not isinstance(result, dict):
            raise TypeError("Metadata extraction did not return a dictionary")

        if "error" in result:
            print(f"❌ Extractor error: {result['error']}")
            update_status(download_id, { "status": "error", "error": result["error"] })
            return result

        if "title" not in result:
            raise ValueError("Missing 'title' in metadata result")

        print(f"✅ Metadata Success: {result['title']}")
        update_status(download_id, { "status": "ready" })
        return result

    except Exception as e:
        print(f"🔥 Exception during metadata fetch for {platform}: {e}")
        traceback.print_exc()
        error_msg = f"❌ Failed to extract metadata: {str(e)}"
        update_status(download_id, { "status": "error", "error": error_msg })
        return { "error": error_msg, "download_id": download_id }


def start_audio_download(url, headers=None, audio_quality="192"):
    download_id = str(uuid.uuid4())
    platform = detect_platform(url)

    print(f"\n[🎵 START AUDIO DOWNLOAD]")
    print(f"🔗 {url}")
    print(f"🛰️ {platform} | 🎧 {audio_quality}K | 🆔 {download_id}")

    service = SERVICE_MAP.get(platform)
    if not service or "audio" not in service:
        error = f"❌ Audio not supported for {platform}"
        print(f"🚫 {error}")
        update_status(download_id, { "status": "error", "error": error })
        return { "error": error, "download_id": download_id }

    try:
        result = service["audio"](url, headers=headers, audio_quality=audio_quality)
        if isinstance(result, dict):
            result.setdefault("download_id", download_id)
        return result
    except Exception as e:
        print(f"🔥 Audio download error: {e}")
        traceback.print_exc()
        error_msg = f"❌ Audio download failed: {str(e)}"
        update_status(download_id, { "status": "error", "error": error_msg })
        return { "error": error_msg, "download_id": download_id }


def start_download(url, resolution, bandwidth_limit=None, headers=None, audio_lang=None):
    download_id = str(uuid.uuid4())
    platform = detect_platform(url)

    print(f"\n[📥 START VIDEO DOWNLOAD]")
    print(f"🔗 {url}")
    print(f"🛰️ {platform} | 🎞️ {resolution} | 🌐 Bandwidth: {bandwidth_limit} | 🗣️ Audio Lang: {audio_lang} | 🆔 {download_id}")

    service = SERVICE_MAP.get(platform)
    if not service or "video" not in service:
        error = f"❌ Video not supported for {platform}"
        print(f"🚫 {error}")
        update_status(download_id, { "status": "error", "error": error })
        return { "error": error, "download_id": download_id }

    try:
        result = service["video"](
            url,
            resolution=resolution,
            headers=headers,
            audio_lang=audio_lang,
            bandwidth_limit=bandwidth_limit
        )
        if isinstance(result, dict):
            result.setdefault("download_id", download_id)
        return result
    except Exception as e:
        print(f"🔥 Video download error: {e}")
        traceback.print_exc()
        error_msg = f"❌ Video download failed: {str(e)}"
        update_status(download_id, { "status": "error", "error": error_msg })
        return { "error": error_msg, "download_id": download_id }


def cancel_download(download_id):
    cancel_event = _download_locks.get(download_id)
    if cancel_event:
        cancel_event.set()
        update_status(download_id, { "status": "cancelled" })
        print(f"⛔ Cancelled download ID: {download_id}")
        return True
    print(f"⚠️ Cancel failed: ID {download_id} not found")
    return False


# --- Internal Management ---

def register_thread(download_id, thread):
    _download_threads[download_id] = thread

def register_cancel_event(download_id, cancel_event):
    _download_locks[download_id] = cancel_event
