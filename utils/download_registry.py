# utils/download_registry.py

# Global maps for tracking threads and cancel events
_download_threads = {}
cancel_event_map = {}

def register_thread(download_id, thread):
    _download_threads[download_id] = thread

def register_cancel_event(download_id, cancel_event):
    cancel_event_map[download_id] = cancel_event

def get_cancel_event(download_id):
    return cancel_event_map.get(download_id)

def get_thread(download_id):
    return _download_threads.get(download_id)

def cancel_download(download_id):
    event = cancel_event_map.get(download_id)
    if event:
        event.set()
        return True
    return False
