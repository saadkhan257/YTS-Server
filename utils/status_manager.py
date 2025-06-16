# 📁 utils/status_manager.py

import os
from threading import Lock
from time import time

_status_map = {}
_timestamp_map = {}
_lock = Lock()

DEFAULT_STATUS = {
    "status": "pending",            # pending / downloading / completed / error / canceled
    "progress": 0.0,                # percent as float
    "speed": "0KB/s",               # human-readable
    "eta": None,                    # estimated time remaining
    "downloaded": 0,                # bytes
    "total": 0,                     # bytes
    "video_url": None,
    "platform": None,
    "phase": None,                  # metadata / download / merge
    "message": None,                # optional message
    "error": None,
    "timestamp": 0,                 # last update
    "created_at": 0,                # creation time
    "completed_at": None,           # when done
    "file_type": "video",           # video / audio
    "filename": None                # actual saved filename
}

# Minimum file size to treat download as valid
MIN_VALID_FILESIZE = 512 * 1024  # 512KB


def _ensure_initialized(download_id: str):
    if download_id not in _status_map:
        now = int(time())
        _status_map[download_id] = DEFAULT_STATUS.copy()
        _status_map[download_id]["created_at"] = now
        _timestamp_map[download_id] = now


def update_status(download_id: str, data: dict):
    with _lock:
        _ensure_initialized(download_id)
        now = int(time())
        _status_map[download_id].update(data)
        _status_map[download_id]["timestamp"] = now
        _timestamp_map[download_id] = now

        # Auto-fill completed timestamp if marked
        if data.get("status") == "completed":
            _status_map[download_id]["completed_at"] = now


def safe_complete(download_id: str, filepath: str = None):
    """
    Safely marks as completed only if the file exists and is valid.
    """
    with _lock:
        _ensure_initialized(download_id)
        now = int(time())

        if filepath and os.path.exists(filepath):
            size = os.path.getsize(filepath)
            if size >= MIN_VALID_FILESIZE:
                _status_map[download_id]["status"] = "completed"
                _status_map[download_id]["completed_at"] = now
                _status_map[download_id]["timestamp"] = now
                _status_map[download_id]["filename"] = os.path.basename(filepath)
                return True
            else:
                update_status(download_id, {
                    "status": "error",
                    "message": f"File too small ({size} bytes), download likely failed.",
                    "error": "incomplete_file"
                })
                return False
        else:
            update_status(download_id, {
                "status": "error",
                "message": "Download file missing or invalid.",
                "error": "missing_file"
            })
            return False


def get_status(download_id: str) -> dict:
    with _lock:
        _ensure_initialized(download_id)
        return _status_map.get(download_id, DEFAULT_STATUS.copy())


def clear_status(download_id: str):
    with _lock:
        _status_map.pop(download_id, None)
        _timestamp_map.pop(download_id, None)


def cleanup_stale_statuses(timeout_seconds=3600):
    with _lock:
        now = int(time())
        stale_ids = [
            did for did, ts in _timestamp_map.items()
            if now - ts > timeout_seconds
        ]
        for did in stale_ids:
            _status_map.pop(did, None)
            _timestamp_map.pop(did, None)


def list_all_statuses(include_meta=False) -> dict:
    with _lock:
        if include_meta:
            return {k: v.copy() for k, v in _status_map.items()}
        else:
            return {
                k: {
                    "status": v["status"],
                    "progress": v["progress"],
                    "speed": v["speed"],
                    "video_url": v["video_url"],
                    "file_type": v.get("file_type", "video"),
                    "filename": v.get("filename")
                }
                for k, v in _status_map.items()
            }


def mark_error(download_id: str, error_message: str):
    update_status(download_id, {
        "status": "error",
        "error": error_message,
        "message": "Download failed",
        "completed_at": int(time())
    })


def mark_cancelled(download_id: str):
    update_status(download_id, {
        "status": "canceled",
        "message": "Download canceled by user",
        "completed_at": int(time())
    })
