import os
import json
import uuid
from threading import Lock
from datetime import datetime
from config import HISTORY_FILE

# Thread lock to avoid race conditions
_history_lock = Lock()
MAX_HISTORY_ENTRIES = 50  # Set the max number of entries to keep

# ✅ Ensure history.json file exists on startup
os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f, indent=2)

# ✅ Read full history (thread-safe internal)
def _read_history() -> list:
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

# ✅ Write history safely (overwrites with trimmed list)
def _write_history(data: list):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data[:MAX_HISTORY_ENTRIES], f, indent=2)

# ✅ Add entry to history
def save_to_history(entry: dict):
    with _history_lock:
        data = _read_history()

        enriched = {
            "id": entry.get("id") or str(uuid.uuid4()),
            "title": entry.get("title", "Untitled"),
            "platform": entry.get("platform", "unknown"),
            "resolution": entry.get("resolution", "N/A"),
            "size": entry.get("size", "N/A"),
            "status": entry.get("status", "completed"),
            "timestamp": datetime.utcnow().isoformat()
        }

        data.insert(0, enriched)
        _write_history(data)

# ✅ Load all history (public safe)
def load_history() -> list:
    with _history_lock:
        return _read_history()

# ✅ Search history by title/platform/status
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

# ✅ Delete single item by ID
def delete_history_item(entry_id: str) -> bool:
    with _history_lock:
        data = _read_history()
        updated = [item for item in data if item.get("id") != entry_id]
        if len(updated) < len(data):
            _write_history(updated)
            return True
        return False

# ✅ Clear full history (used by hourly cleanup)
def clear_history():
    with _history_lock:
        _write_history([])

# ✅ Return latest N items
def get_recent_history(limit: int = 10) -> list:
    with _history_lock:
        return _read_history()[:limit]
