import subprocess
import os
import tempfile
import json

def combine_videos(video1_path, video2_path):
    """
    Combine two video files with their audio using FFmpeg,
    starting the second video after the first one ends.

    :param video1_path: Path to the first video file
    :param video2_path: Path to the second video file
    :return: Path to the temporary file containing the combined video
    """
    # Ensure input files exist
    if not os.path.exists(video1_path) or not os.path.exists(video2_path):
        raise FileNotFoundError("One or both input video files do not exist.")

    # Get duration of the first video
    duration_command = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'json',
        video1_path
    ]
    duration_output = subprocess.check_output(duration_command, universal_newlines=True)
    duration = json.loads(duration_output)['format']['duration']

    # Create a temporary file for the output video
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as output_file:
        output_path = output_file.name

    try:
        # FFmpeg command to combine videos
        ffmpeg_command = [
            'ffmpeg',
            '-i', video1_path,
            '-i', video2_path,
            '-filter_complex',
            f'[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[outv][outa]',
            '-map', '[outv]',
            '-map', '[outa]',
            '-c:v', 'libx264',
            '-crf', '23',
            '-preset', 'medium',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-y',
            output_path
        ]

        # Execute FFmpeg command
        result = subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)

        print(f"Videos combined successfully. Output saved to temporary file: {output_path}")
        print(f"FFmpeg output: {result.stdout}")

        return output_path

    except subprocess.CalledProcessError as e:
        print(f"Error occurred while combining videos: {e.stderr}")
        if os.path.exists(output_path):
            os.unlink(output_path)
        raise

# Example usage:
# combined_video_path = combine_videos('path/to/video1.mp4', 'path/to/video2.mp4')
# ... use the combined video ...
# os.unlink(combined_video_path)  # Delete the temporary file when done