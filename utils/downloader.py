import os
import uuid
import threading
import traceback

from config import VIDEO_DIR, AUDIO_DIR, SERVER_URL
from utils.platform_helper import detect_platform
from utils.status_manager import update_status

# Platform service imports
from services.yt_service import (
    extract_yt_metadata,
    start_yt_audio_download,
    start_yt_video_download
)

from services.tt_service import (
    extract_tt_metadata,
    start_tt_audio_download,
    start_tt_video_download
)

from services.fb_service import (
    extract_fb_metadata,
    start_fb_audio_download,
    start_fb_video_download
)

from services.x_service import (
    extract_x_metadata,
    start_x_audio_download,
    start_x_video_download
)

from services.ig_service import (
    extract_ig_metadata,
    start_ig_audio_download,
    start_ig_video_download
)

# Internal state tracking
_download_threads = {}
_download_locks = {}

# Service mapping
SERVICE_MAP = {
    "youtube": {
        "meta": extract_yt_metadata,
        "audio": start_yt_audio_download,
        "video": start_yt_video_download
    },
    "tiktok": {
        "meta": extract_tt_metadata,
        "audio": start_tt_audio_download,
        "video": start_tt_video_download
    },
    "facebook": {
        "meta": extract_fb_metadata,
        "audio": start_fb_audio_download,
        "video": start_fb_video_download
    },
    "x": {
        "meta": extract_x_metadata,
        "audio": start_x_audio_download,
        "video": start_x_video_download
    },
    "instagram": {
        "meta": extract_ig_metadata,
        "audio": start_ig_audio_download,
        "video": start_ig_video_download
    },
}

# --- Public APIs ---

def get_video_info(url, headers=None, download_id=None):
    platform = detect_platform(url)
    service = SERVICE_MAP.get(platform)

    if not service:
        return {
            "error": f"❌ Unsupported platform: {platform}",
            "download_id": download_id or str(uuid.uuid4())
        }

    try:
        result = service["meta"](url, headers=headers, download_id=download_id)
        if "error" in result:
            print(f"[❌ METADATA] Platform: {platform}, Error: {result['error']}")
        return result
    except Exception as e:
        print(f"[❌ METADATA EXCEPTION] {platform}: {str(e)}")
        traceback.print_exc()
        return {
            "error": f"❌ Failed to extract metadata from {platform}: {str(e)}",
            "download_id": download_id or str(uuid.uuid4())
        }


def start_audio_download(url, headers=None, audio_quality="192"):
    platform = detect_platform(url)
    service = SERVICE_MAP.get(platform)

    if not service or "audio" not in service:
        return {"error": f"❌ Audio download not supported for {platform}"}

    try:
        return service["audio"](url, headers=headers, audio_quality=audio_quality)
    except Exception as e:
        print(f"[❌ AUDIO ERROR] Platform: {platform}, Error: {str(e)}")
        traceback.print_exc()
        return {"error": f"❌ Audio download failed on {platform}: {str(e)}"}


def start_download(url, resolution, bandwidth_limit=None, headers=None, audio_lang=None):
    platform = detect_platform(url)
    service = SERVICE_MAP.get(platform)

    if not service or "video" not in service:
        return {"error": f"❌ Video download not supported for {platform}"}

    try:
        return service["video"](
            url,
            resolution=resolution,
            headers=headers,
            audio_lang=audio_lang,
            bandwidth_limit=bandwidth_limit
        )
    except Exception as e:
        print(f"[❌ VIDEO ERROR] Platform: {platform}, Error: {str(e)}")
        traceback.print_exc()
        return {"error": f"❌ Video download failed on {platform}: {str(e)}"}


def cancel_download(download_id):
    cancel_event = _download_locks.get(download_id)
    if cancel_event:
        cancel_event.set()
        update_status(download_id, {"status": "cancelled"})
        return True
    return False

# --- Internal Registration ---

def register_thread(download_id, thread):
    _download_threads[download_id] = thread

def register_cancel_event(download_id, cancel_event):
    _download_locks[download_id] = cancel_event
