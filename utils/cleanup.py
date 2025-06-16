import os
import time
import shutil
import json
from datetime import datetime, timedelta
from config import VIDEO_DIR, AUDIO_DIR
from utils.history_manager import HISTORY_FILE

# Delete files older than this
DELETE_AFTER = timedelta(days=1)

# Run cleanup every hour
CLEANUP_INTERVAL = 3600  # in seconds

# Directories to clean
TARGET_DIRS = [VIDEO_DIR, AUDIO_DIR]

def cleanup_old_files():
    print(f"[CLEANUP] 🔁 Hourly cleanup thread started... Watching: {TARGET_DIRS}")

    while True:
        for directory in TARGET_DIRS:
            run_cleanup_once(directory)

        clean_history_file()
        time.sleep(CLEANUP_INTERVAL)

def run_cleanup_once(directory):
    now = datetime.now()
    deleted_files = 0
    deleted_dirs = 0
    total_size_freed = 0
    type_counts = {}

    print(f"\n[CLEANUP] 🔍 Scanning: {directory}")

    try:
        for root, dirs, files in os.walk(directory, topdown=False):
            # 🔹 Clean files
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    if not os.path.isfile(file_path):
                        continue

                    modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                    file_age = now - modified
                    file_size = os.path.getsize(file_path)

                    # Only delete if older than threshold or size == 0
                    if file_age > DELETE_AFTER or file_size == 0:
                        ext = os.path.splitext(file)[1].lower()
                        type_counts[ext] = type_counts.get(ext, 0) + 1
                        total_size_freed += file_size
                        os.remove(file_path)
                        print(f"[CLEANUP] 🗑️ Deleted: {file_path}")
                        deleted_files += 1

                except Exception as fe:
                    print(f"[CLEANUP ERROR] Failed to delete {file_path}: {fe}")

            # 🔹 Clean empty folders
            for dir in dirs:
                dir_path = os.path.join(root, dir)
                try:
                    if os.path.isdir(dir_path) and not os.listdir(dir_path):
                        shutil.rmtree(dir_path)
                        print(f"[CLEANUP] 🧹 Removed folder: {dir_path}")
                        deleted_dirs += 1
                except Exception as de:
                    print(f"[CLEANUP ERROR] Failed to delete folder {dir_path}: {de}")

        print(f"\n[CLEANUP DONE] ✅ {directory}")
        print(f"🗂️  Files deleted: {deleted_files}")
        print(f"📁 Folders deleted: {deleted_dirs}")
        print(f"💾 Space freed: {round(total_size_freed / 1024 / 1024, 2)} MB")
        print(f"📦 File types: {type_counts}")
        print("-" * 50)

    except Exception as e:
        print(f"[CLEANUP ERROR] ❌ Could not scan {directory}: {e}")

def clean_history_file():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "w") as f:
                json.dump([], f)
            print(f"[HISTORY CLEANUP] 🧾 history.json has been cleared.")
    except Exception as e:
        print(f"[HISTORY CLEANUP ERROR] ❌ Failed to clear history.json: {e}")
