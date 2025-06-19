# downloader.py

import os
import uuid
import threading
import importlib
import inspect

from config import VIDEO_DIR, AUDIO_DIR
from utils.platform_helper import detect_platform
from utils.status_manager import update_status

# --- Global Setup ---
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

GLOBAL_PROXY = os.getenv("YTS_PROXY") or None
_download_threads = {}
_download_locks = {}

# --- Auto Service Loader ---

SERVICE_MAP = {}

def _load_all_services():
    import services
    for name in dir(services):
        if name.endswith("_service"):
            module = getattr(services, name)
            platform = name.replace("_service", "")
            if inspect.ismodule(module):
                SERVICE_MAP[platform] = module

_load_all_services()

# --- Unified Dispatch Logic ---

def _get_service_function(platform, function_suffix):
    service = SERVICE_MAP.get(platform)
    if not service:
        raise Exception(f"❌ Unsupported platform: {platform}")
    fn_name = f"{function_suffix}_{platform}_{'download' if 'download' in function_suffix else 'metadata'}"
    if not hasattr(service, fn_name):
        raise Exception(f"❌ Function `{fn_name}` not found in {platform}_service.py")
    return getattr(service, fn_name)

# --- Public API Functions ---

def extract_metadata(url, headers=None, download_id=None):
    platform = detect_platform(url)
    fn = _get_service_function(platform, "extract")
    return fn(url=url, headers=headers, download_id=download_id)

def start_download(url, resolution, bandwidth_limit=None, headers=None, audio_lang=None):
    platform = detect_platform(url)
    fn = _get_service_function(platform, "start")
    return fn(
        url=url,
        resolution=resolution,
        headers=headers,
        bandwidth_limit=bandwidth_limit,
        audio_lang=audio_lang
    )

def start_audio_download(url, headers=None, audio_quality='192'):
    platform = detect_platform(url)
    fn = _get_service_function(platform, "start_audio")
    return fn(
        url=url,
        headers=headers,
        audio_quality=audio_quality
    )

# --- Download Control Functions ---

def cancel_download(download_id):
    cancel_event = _download_locks.get(download_id)
    if cancel_event:
        cancel_event.set()
        update_status(download_id, {"status": "cancelled"})
        return True
    return False

def pause_download(download_id):
    # Placeholder for future pause
    return False

def resume_download(download_id):
    # Placeholder for future resume
    return False

def get_video_info(url, headers=None, download_id=None):
    return extract_metadata(url, headers=headers, download_id=download_id)

# --- Thread Access (shared for services) ---

def get_download_thread_map():
    return _download_threads, _download_locks
