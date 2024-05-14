import subprocess
import tempfile
import shutil
import os


class VideoClipper:
    def __init__(self):
        pass

    def format_time(self, seconds):
        # Converts time in seconds to a string format acceptable by FFmpeg (hh:mm:ss.ms)
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:06.3f}"

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

    def delete_segments_from_video(self, input_video_path, segments_to_keep, output_video_path):
        filter_complex = []
        inputs = []
        for i, (start, end) in enumerate(segments_to_keep):
            # Format start and end times for FFmpeg
            start_formatted = self.format_time(start)
            end_formatted = self.format_time(end)

            # Create filters to extract segments
            filter_complex.append(f"[0:v]trim=start={start_formatted}:end={end_formatted},setpts=PTS-STARTPTS[v{i}];")
            filter_complex.append(f"[0:a]atrim=start={start_formatted}:end={end_formatted},asetpts=PTS-STARTPTS[a{i}];")
            inputs.append(f"[v{i}][a{i}]")

        # Concatenate the video segments
        concat_str = 'concat:' + '|'.join(f'n={len(segments_to_keep)}:v=1:a=1[vout][aout]')
        filter_complex.append(f"{concat_str}")

        # Build the complete FFmpeg command
        ffmpeg_command = [
            'ffmpeg',
            '-y',  # Overwrite output files without asking
            '-i', input_video_path,
            '-filter_complex', ''.join(filter_complex),
            '-map', '[vout]',
            '-map', '[aout]',
            '-c:v', 'libx264',
            '-crf', '23',
            '-preset', 'fast',
            output_video_path
        ]

        # Execute the command
        subprocess.run(ffmpeg_command, check=True)
