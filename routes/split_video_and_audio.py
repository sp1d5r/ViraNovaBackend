
import subprocess
from tempfile import NamedTemporaryFile
import os

def extract_audio_from_video(video_bytes):
    # Create a temporary file for the video
    with NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_video:
        tmp_video_name = tmp_video.name
        tmp_video.write(video_bytes.getbuffer())

    # Define the temporary audio file name
    tmp_audio_name = tmp_video_name.replace('.mp4', '_audio.mp4')

    # Use FFmpeg to extract audio
    subprocess.run([
        'ffmpeg',
        '-i', tmp_video_name,  # Input video file
        '-vn',
        '-acodec', 'pcm_s16le',  # Use Linear PCM format
        '-ar', '16000',  # Set sample rate to 16000 Hz
        '-ac', '1',  # Set audio channels to mono
        tmp_audio_name  # Output audio file name
    ], check=True)

    # Read the audio file back into memory
    with open(tmp_audio_name, 'rb') as audio_file:
        audio_bytes = audio_file.read()

    # Cleanup temporary files
    os.remove(tmp_video_name)
    os.remove(tmp_audio_name)

    return audio_bytes
