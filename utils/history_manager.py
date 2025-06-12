# 📁 utils/history_manager.py

import os
import json
import uuid
from threading import Lock
from datetime import datetime
from config import HISTORY_FILE

_history_lock = Lock()
MAX_HISTORY_ENTRIES = 50  # configurable

# ✅ Ensure history file exists
if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f, indent=2)

def _read_history() -> list:
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def _write_history(data: list):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data[:MAX_HISTORY_ENTRIES], f, indent=2)

# ✅ Save an entry to history
def save_to_history(entry: dict):
    with _history_lock:
        data = _read_history()

        entry = {
            "id": entry.get("id") or str(uuid.uuid4()),
            "title": entry.get("title", "Untitled"),
            "platform": entry.get("platform", "unknown"),
            "resolution": entry.get("resolution", "N/A"),
            "size": entry.get("size", "N/A"),
            "status": entry.get("status", "completed"),
            "timestamp": datetime.utcnow().isoformat()
        }

        data.insert(0, entry)
        _write_history(data)

# ✅ Load entire history
def load_history() -> list:
    with _history_lock:
        return _read_history()

# ✅ Filter history
def search_history(keyword: str = "", platform: str = "", status: str = "") -> list:
    with _history_lock:
        data = _read_history()
        keyword = keyword.lower()
        platform = platform.lower()
        status = status.lower()

        return [
            item for item in data
            if (not keyword or keyword in item.get("title", "").lower())
            and (not platform or item.get("platform", "").lower() == platform)
            and (not status or item.get("status", "").lower() == status)
        ]

# ✅ Delete specific entry
def delete_history_item(entry_id: str) -> bool:
    with _history_lock:
        data = _read_history()
        filtered = [item for item in data if item.get("id") != entry_id]
        if len(filtered) < len(data):
            _write_history(filtered)
            return True
        return False

# ✅ Clear all history
def clear_history():
    with _history_lock:
        _write_history([])

# ✅ Get recent N entries
def get_recent_history(limit: int = 10) -> list:
    with _history_lock:
        return _read_history()[:limit]
