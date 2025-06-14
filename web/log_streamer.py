import os
import time
import threading
from queue import Queue

LOG_FILE_PATH = "/var/log/syslog"  # 🔁 Change this to your actual log file (e.g., gunicorn log or custom app log)
log_queue = Queue()

def tail_log(file_path=LOG_FILE_PATH):
    """Tail the specified log file and stream lines to the queue."""
    if not os.path.exists(file_path):
        log_queue.put("[ERROR] Log file not found: " + file_path)
        return

    with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
        file.seek(0, os.SEEK_END)  # Go to the end of file
        while True:
            line = file.readline()
            if not line:
                time.sleep(0.1)  # Wait for new data
                continue
            log_queue.put(line.strip())

def get_log_line():
    """Get the next log line from the queue (non-blocking)."""
    try:
        return log_queue.get_nowait()
    except:
        return None

def start_log_thread():
    """Start the log tailer in a daemon thread."""
    threading.Thread(target=tail_log, daemon=True).start()
