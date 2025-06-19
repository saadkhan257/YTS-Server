# utils/download_registry.py

_download_threads = {}
_download_locks = {}

def register_thread(download_id, thread):
    _download_threads[download_id] = thread

def register_cancel_event(download_id, cancel_event):
    _download_locks[download_id] = cancel_event

def get_cancel_event(download_id):
    return _download_locks.get(download_id)

def get_thread(download_id):
    return _download_threads.get(download_id)

def cancel_download(download_id):
    event = _download_locks.get(download_id)
    if event:
        event.set()
