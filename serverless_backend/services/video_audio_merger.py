from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_audioclips, CompositeAudioClip
import tempfile
import os


class VideoAudioMerger:
    @staticmethod
    def merge_audio_to_video(video_path, audio_path, volume_percent, start_time=None, audio_duration=None, repeat=True):
        # Load video
        video = VideoFileClip(video_path)
        original_audio = video.audio if video.audio is not None else None

        # Load background audio
        background_audio = AudioFileClip(audio_path)

        # Adjust the volume of the background audio
        volume_factor = volume_percent / 100.0
        background_audio = background_audio.volumex(volume_factor)

        # Determine the subclip of the background audio to use
        if start_time is not None and audio_duration is not None:
            background_audio = background_audio.subclip(start_time, start_time + audio_duration)
        elif start_time is not None:
            background_audio = background_audio.subclip(start_time)

        # Loop background audio if necessary to match video duration and if repeat is True
        if repeat and background_audio.duration < video.duration:
            loops_required = int(video.duration / background_audio.duration) + 1
            background_audio = concatenate_audioclips([background_audio] * loops_required)

        # Ensure the background audio matches exactly the duration of the video
        background_audio = background_audio.set_duration(video.duration)

        # Combine the original audio (if exists) with the new background audio
        if original_audio:
            final_audio = CompositeAudioClip([original_audio, background_audio])
        else:
            final_audio = background_audio

        # Set the final audio to the video
        video = video.set_audio(final_audio)

        # Output the video file using a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4', dir=os.path.dirname(video_path)) as tmpfile:
            output_path = tmpfile.name
            video.write_videofile(output_path, codec='libx264', audio_codec='aac', temp_audiofile="/tmp/random_audio_merger.mp3")

        return output_path
