import subprocess
import tempfile
import shutil
import os
from moviepy.editor import VideoFileClip, concatenate_videoclips


class VideoClipper:
    def __init__(self):
        pass

    def format_time(self, seconds):
        # Converts time in seconds to a string format acceptable by FFmpeg (hh:mm:ss.ms)
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:06.3f}"

    def get_video_duration(self, video_path):
        # Open the video file with MoviePy and return its duration
        with VideoFileClip(video_path) as video:
            return video.duration

    def clip_video(self, input_path, start_time, end_time, output_path):
        # Format times as strings, e.g., '00:00:10'
        start_str = self.format_time(start_time)
        end_str = self.format_time(end_time)

        command = [
            'ffmpeg',
            '-y',
            '-ss', start_str,
            '-to', end_str,
            '-i', input_path,
            '-c:v', 'libx264',
            '-crf', '23',
            '-preset', 'fast',
            output_path
        ]

        subprocess.run(command, check=True)

    def clip_and_replace_video(self, original_path, start_time, end_time):
        # Create a temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix='.mp4')

        try:
            # Format times as strings, e.g., '00:00:10'
            start_str = self.format_time(start_time)
            end_str = self.format_time(end_time)

            # FFmpeg command to clip the video
            command = [
                'ffmpeg',
                '-y',
                '-ss', start_str,
                '-to', end_str,
                '-i', original_path,
                '-c:v', 'libx264',
                '-crf', '23',
                '-preset', 'fast',
                temp_path
            ]

            # Run the FFmpeg command
            subprocess.run(command, check=True)

            # Move the temporary file to the original file location, effectively replacing it
            shutil.move(temp_path, original_path)

        finally:
            # Ensure the temporary file is closed and removed
            os.close(temp_fd)
            os.remove(temp_path)

    def delete_segments_from_video(self, input_video_path, segments_to_keep, output_video_path, update_progress):
        # Load the source video
        video = VideoFileClip(input_video_path)

        # List to store the clips to concatenate
        clips = []

        # Extract clips to keep from the video
        for index, (start, end) in enumerate(segments_to_keep):
            clips.append(video.subclip(start, end))
            update_progress((index / len(segments_to_keep))*100)

        # Concatenate the clips
        final_clip = concatenate_videoclips(clips)

        # Write the result to the output file
        final_clip.write_videofile(output_video_path, codec="libx264", fps=24, preset="fast")

