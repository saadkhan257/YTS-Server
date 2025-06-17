import os
import subprocess
import uuid

def convert_video_to_mp3(input_path, output_dir):
    """
    Converts a video file to high-quality MP3 using FFmpeg.

    Args:
        input_path (str): Path to the input video file.
        output_dir (str): Directory to save the converted MP3.

    Returns:
        str: Path to the resulting MP3 file.

    Raises:
        RuntimeError: If FFmpeg fails to convert the file.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    base_filename = os.path.splitext(os.path.basename(input_path))[0]
    unique_suffix = str(uuid.uuid4())[:6]
    output_filename = f"{base_filename}_{unique_suffix}.mp3"
    output_path = os.path.join(output_dir, output_filename)

    command = [
        "ffmpeg",
        "-y",                    # Overwrite output if exists
        "-i", input_path,        # Input file
        "-vn",                   # No video
        "-acodec", "libmp3lame", # MP3 codec
        "-ab", "192k",           # Audio bitrate
        output_path
    ]

    try:
        print(f"[FFMPEG] Converting to MP3: {output_path}")
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg failed to convert to MP3: {e}")
