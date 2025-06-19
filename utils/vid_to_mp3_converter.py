import os
import subprocess
import uuid
import traceback

AUDIO_DIR = os.path.join("static", "audios")
os.makedirs(AUDIO_DIR, exist_ok=True)

def convert_video_to_mp3(input_path, target_bitrate="192", slug=None):
    try:
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Unique filename
        video_id = slug or str(uuid.uuid4())[:8]
        filename = f"audio_{video_id}_{target_bitrate}k.mp3"
        output_path = os.path.join(AUDIO_DIR, filename)

        # FFmpeg command
        command = [
            "ffmpeg",
            "-y",  # Overwrite without asking
            "-i", input_path,
            "-vn",  # No video
            "-acodec", "libmp3lame",
            "-ab", f"{target_bitrate}k",
            "-ar", "44100",  # Audio sampling rate
            "-loglevel", "error",
            output_path
        ]

        print(f"[🔄 FFmpeg] Converting {input_path} → {output_path} at {target_bitrate}K")

        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg error:\n{result.stderr.decode()}")

        if not os.path.exists(output_path) or os.path.getsize(output_path) < 100 * 1024:
            raise Exception("Output file missing or too small after conversion.")

        print(f"[✅ FFmpeg] Conversion done: {output_path}")
        return output_path

    except Exception as e:
        print(f"[❌ MP3 CONVERT ERROR] {e}")
        traceback.print_exc()
        return None
