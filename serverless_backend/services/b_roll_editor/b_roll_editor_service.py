import os
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
import requests
from io import BytesIO
import tempfile
from PIL import Image
import numpy as np
import imghdr



class BRollEditorService:
    def __init__(self, firebase_services, fps=30):
        self.fps = fps
        self.firebase_services = firebase_services
        self.a_roll_duration = 0
        # Ensure we're using /tmp for all temporary files
        tempfile.tempdir = "/tmp"

    def download_media(self, src, upload_type):
        try:
            if upload_type == 'link':
                response = requests.get(src)
                content_type = response.headers.get('content-type', '')
                print(f"Downloaded content type: {content_type}")
                return BytesIO(response.content), content_type
            elif upload_type == 'upload':
                temp_file = tempfile.NamedTemporaryFile(delete=False, dir="/tmp")
                self.firebase_services.download_file(src, temp_file.name)
                return temp_file.name, None
            else:
                raise ValueError(f"Unknown upload type: {upload_type}")
        except Exception as e:
            print(f"Error downloading media: {str(e)}")
            raise

    def create_media_clip(self, item, total_frames):
        try:
            object_metadata = item['objectMetadata']
            start_frame = item['start']
            end_frame = item['end']

            start_time = start_frame / self.fps
            end_time = end_frame / self.fps
            intended_duration = end_time - start_time

            media_source, content_type = self.download_media(object_metadata['src'], object_metadata['uploadType'])

            if object_metadata['type'] == 'image':
                media = self.process_image(media_source, content_type, intended_duration)
            else:  # video
                media = self.process_video(media_source, object_metadata, intended_duration)

            # Resize and position the media
            media = (media
                     .resize(height=object_metadata['height'])
                     .resize(width=object_metadata['width'])
                     .set_position((object_metadata['x'], object_metadata['y']))
                     .set_start(start_time))

            # If it's a file path, we need to clean it up
            if isinstance(media_source, str):
                os.unlink(media_source)

            return media
        except Exception as e:
            print(f"Error creating media clip: {str(e)}")
            return self.create_placeholder_image(intended_duration)

    def process_image(self, media_source, content_type, intended_duration):
        if isinstance(media_source, BytesIO):
            media_source.seek(0)
            img_type = imghdr.what(media_source)
            print(f"Detected image type: {img_type}")

            if img_type is None or 'image' not in content_type:
                print(f"Invalid image data")
                return self.create_placeholder_image(intended_duration)

            try:
                media_source.seek(0)
                image = Image.open(media_source)
                image_array = np.array(image)
                return ImageClip(image_array).set_duration(intended_duration)
            except Exception as e:
                print(f"Error opening image: {e}")
                return self.create_placeholder_image(intended_duration)
        else:  # It's a file path
            try:
                return ImageClip(media_source).set_duration(intended_duration)
            except Exception as e:
                print(f"Error opening image file: {e}")
                return self.create_placeholder_image(intended_duration)

    def process_video(self, media_source, object_metadata, intended_duration):
        try:
            video_clip = VideoFileClip(media_source)
            offset = object_metadata.get('offset', 0)  # Get offset in seconds, default to 0
            available_duration = video_clip.duration - offset
            if available_duration <= 0:
                raise ValueError("Offset is greater than or equal to video duration")

            actual_duration = min(intended_duration, available_duration)
            media = video_clip.subclip(offset, offset + actual_duration)

            if actual_duration < intended_duration:
                print(f"B-roll video is shorter than intended duration. It will end early.")
                media = media.set_duration(actual_duration)
            return media
        except Exception as e:
            print(f"Error processing video: {e}")
            return self.create_placeholder_image(intended_duration)

    def create_placeholder_image(self, duration):
        color = (np.random.rand(3) * 255).astype(int)
        placeholder = ImageClip(np.full((100, 100, 3), color, dtype=np.uint8))
        return placeholder.set_duration(duration)

    def __call__(self, input_video_path, b_roll_tracks, update_progress):
        try:
            print(f"Loading A-roll video from {input_video_path}")
            video = VideoFileClip(input_video_path)
        except Exception as e:
            print(f"Error loading A-roll video: {e}")
            raise

        self.fps = video.fps
        self.a_roll_duration = video.duration
        total_frames = int(self.a_roll_duration * self.fps)

        b_roll_clips = []
        total_items = sum(len(track['items']) for track in b_roll_tracks)
        processed_items = 0

        for track in b_roll_tracks:
            for item in track['items']:
                try:
                    clip = self.create_media_clip(item, total_frames)
                    b_roll_clips.append(clip)
                except Exception as e:
                    print(f"Error creating clip for item: {item}")
                    print(f"Error details: {e}")
                processed_items += 1
                update_progress(20 + (60 * processed_items / total_items))

        final_video = CompositeVideoClip([video] + b_roll_clips)

        try:
            temp_output_file = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False, dir="/tmp")
            print(f"Writing final video to {temp_output_file.name}")
            final_video.write_videofile(temp_output_file.name, codec='libx264', audio_codec='aac', fps=self.fps, temp_audiofile="/tmp/b_roll_temp_audio.m4a")
            return temp_output_file.name
        except Exception as e:
            print(f"Error writing final video: {e}")
            raise