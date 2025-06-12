# 📁 utils/cleanup.py

import os
import time
import shutil
from datetime import datetime, timedelta
from config import VIDEO_DIR

DELETE_AFTER = timedelta(days=1)
CLEANUP_INTERVAL = 3600  # every hour

def cleanup_old_videos():
    print(f"[CLEANUP] 🔁 Starting hourly cleanup loop...")

    while True:
        run_cleanup_once()
        time.sleep(CLEANUP_INTERVAL)

def run_cleanup_once():
    now = datetime.now()
    deleted_files = 0
    deleted_dirs = 0
    total_size_freed = 0
    type_counts = {}

    try:
        for root, dirs, files in os.walk(VIDEO_DIR, topdown=False):
            # 🔹 Clean files
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    if not os.path.isfile(file_path):
                        continue

                    modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                    file_size = os.path.getsize(file_path)

                    if now - modified > DELETE_AFTER or file_size == 0:
                        ext = os.path.splitext(file)[1].lower()
                        type_counts[ext] = type_counts.get(ext, 0) + 1
                        total_size_freed += file_size
                        os.remove(file_path)
                        print(f"[CLEANUP] 🗑️ Deleted file: {file}")
                        deleted_files += 1

                except Exception as fe:
                    print(f"[CLEANUP ERROR] Failed to delete file {file}: {fe}")

            # 🔹 Clean empty directories
            for dir in dirs:
                dir_path = os.path.join(root, dir)
                try:
                    if os.path.isdir(dir_path) and not os.listdir(dir_path):
                        shutil.rmtree(dir_path)
                        print(f"[CLEANUP] 🧹 Removed empty folder: {dir}")
                        deleted_dirs += 1
                except Exception as de:
                    print(f"[CLEANUP ERROR] Failed to delete folder {dir}: {de}")

        print(f"\n[CLEANUP COMPLETE] ✅")
        print(f"🗂️  Files deleted: {deleted_files}")
        print(f"📁 Folders deleted: {deleted_dirs}")
        print(f"💾 Total size freed: {round(total_size_freed / 1024 / 1024, 2)} MB")
        print(f"📦 Types deleted: {type_counts}")
        print("-" * 40 + "\n")

    except Exception as e:
        print(f"[CLEANUP ERROR] ❌ Could not scan VIDEO_DIR: {e}")
