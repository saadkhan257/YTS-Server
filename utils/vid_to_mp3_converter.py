import os
import subprocess

def convert_to_mp3(input_path, output_path):
    try:
        cmd = [
            "ffmpeg",
            "-y",  # overwrite
            "-i", input_path,
            "-vn",
            "-ab", "192k",
            "-ar", "44100",
            "-f", "mp3",
            output_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return output_path
    except Exception as e:
        print(f"[FFMPEG ERROR] {e}")
        raise
