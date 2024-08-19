import cv2
import os
import tempfile
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import subprocess
import unicodedata


class AddTextToVideoService:
    def __init__(self):
        self.font_base_path = 'serverless_backend/assets/fonts'
        self.emoji_font_path = 'serverless_backend/assets/fonts/AppleColorEmoji.ttf'

    def _get_video_info(self, input_path):
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise ValueError("Error: Could not open video.")
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        return fps, width, height, total_frames

    def _is_emoji(self, character):
        return unicodedata.category(character) == 'So'

    def _get_font(self, text, max_width, max_height, thickness, font_scale):
        font_path = os.path.abspath(os.path.join(self.font_base_path, f'Montserrat-{thickness}.ttf'))
        if not os.path.exists(font_path):
            raise FileNotFoundError(f"Error: Font file not found at {font_path}")

        font_size = int(font_scale * 20)
        font = ImageFont.truetype(font_path, font_size)
        emoji_font = ImageFont.truetype(self.emoji_font_path, font_size)

        while True:
            bbox = ImageDraw.Draw(Image.new('RGB', (1, 1))).textbbox((0, 0), text, font=font)
            if bbox[2] - bbox[0] <= max_width and bbox[3] - bbox[1] <= max_height:
                break
            font_size -= 1
            if font_size <= 0:
                raise ValueError("Error: Text is too large to fit in the video")
            font = ImageFont.truetype(font_path, font_size)
            emoji_font = ImageFont.truetype(self.emoji_font_path, font_size)

        return font, emoji_font

    def _process_frame(self, frame, text, font, emoji_font, position, color, shadow_offset, shadow_color, outline,
                       outline_color, outline_thickness):
        pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_image)

        def draw_text_with_effects(pos, text_color):
            x, y = pos
            for char in text:
                if self._is_emoji(char):
                    draw.text((x, y), char, font=emoji_font, fill=text_color)
                    x += emoji_font.getsize(char)[0]
                else:
                    draw.text((x, y), char, font=font, fill=text_color)
                    x += font.getsize(char)[0]

        # Draw shadow
        draw_text_with_effects((position[0] + shadow_offset[0], position[1] + shadow_offset[1]), shadow_color)

        # Draw outline
        if outline:
            for x in range(-outline_thickness, outline_thickness + 1):
                for y in range(-outline_thickness, outline_thickness + 1):
                    if x != 0 or y != 0:
                        draw_text_with_effects((position[0] + x, position[1] + y), outline_color)

        # Draw main text
        draw_text_with_effects(position, color)

        return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

    def add_text_centered(self, input_path, text, font_scale, position=None, color=(255, 255, 255), thickness='Bold',
                          shadow_offset=(2, 2), shadow_color=(0, 0, 0), outline=False, outline_color=(0, 0, 0),
                          outline_thickness=2, offset=None, start_seconds=None, end_seconds=None):
        fps, width, height, total_frames = self._get_video_info(input_path)

        font, emoji_font = self._get_font(text, width, height, thickness, font_scale)

        bbox = ImageDraw.Draw(Image.new('RGB', (1, 1))).textbbox((0, 0), text, font=font)
        text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]

        if position is None:
            position = ((width - text_width) // 2, (height - text_height) // 2)

        if offset is not None:
            position = (
                position[0] + int(width * offset[0]),
                position[1] + int(height * offset[1])
            )

        with tempfile.NamedTemporaryFile(suffix='.yuv', delete=False) as raw_file:
            raw_path = raw_file.name

        cap = cv2.VideoCapture(input_path)
        frame_count = 0

        with open(raw_path, 'wb') as raw_out:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if start_seconds is None or end_seconds is None or (
                        start_seconds * fps <= frame_count <= end_seconds * fps):
                    frame = self._process_frame(frame, text, font, emoji_font, position, color, shadow_offset,
                                                shadow_color,
                                                outline, outline_color, outline_thickness)

                yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
                raw_out.write(yuv.tobytes())
                frame_count += 1

        cap.release()

        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as output_file:
            output_path = output_file.name

        ffmpeg_command = [
            'ffmpeg',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{width}x{height}',
            '-pix_fmt', 'yuv420p',
            '-r', str(fps),
            '-i', raw_path,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-y',
            output_path
        ]

        subprocess.run(ffmpeg_command, check=True)

        os.remove(raw_path)
        os.remove(input_path)
        print("Centered text added to video, original file updated!")
        return output_path

    def add_text(self, input_path, text, font_scale, position, color, thickness, start_seconds=None, end_seconds=None,
                 shadow_offset=(2, 2), shadow_color=(0, 0, 0), outline=False, outline_color=(0, 0, 0),
                 outline_thickness=2, offset=None):
        fps, width, height, total_frames = self._get_video_info(input_path)

        font, emoji_font = self._get_font(text, width, height, thickness, font_scale)

        if offset is not None:
            bbox = ImageDraw.Draw(Image.new('RGB', (1, 1))).textbbox((0, 0), text, font=font)
            text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
            position = (
                (width // 2) + int(width * offset[0]) - (text_width // 2),
                (height // 2) + int(height * offset[1]) - (text_height // 2)
            )

        if position is None:
            position = (50, 50)

        with tempfile.NamedTemporaryFile(suffix='.yuv', delete=False) as raw_file:
            raw_path = raw_file.name

        cap = cv2.VideoCapture(input_path)
        frame_count = 0

        with open(raw_path, 'wb') as raw_out:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if start_seconds is None or end_seconds is None or (
                        start_seconds * fps <= frame_count <= end_seconds * fps):
                    frame = self._process_frame(frame, text, font, emoji_font, position, color, shadow_offset,
                                                shadow_color,
                                                outline, outline_color, outline_thickness)

                yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
                raw_out.write(yuv.tobytes())
                frame_count += 1

        cap.release()

        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as output_file:
            output_path = output_file.name

        ffmpeg_command = [
            'ffmpeg',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{width}x{height}',
            '-pix_fmt', 'yuv420p',
            '-r', str(fps),
            '-i', raw_path,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-y',
            output_path
        ]

        subprocess.run(ffmpeg_command, check=True)

        os.remove(raw_path)
        os.remove(input_path)
        print("Text added to video, original file updated!")
        return output_path

    def add_transcript(self, input_path, texts, start_times, end_times, font_scale=1, color=(255, 255, 255),
                       thickness='Bold', shadow_offset=(2, 2), shadow_color=(0, 0, 0), outline=False,
                       outline_color=(0, 0, 0), outline_thickness=2, offset=(0, 0)):
        fps, width, height, total_frames = self._get_video_info(input_path)

        fonts_and_emoji_fonts = [self._get_font(text, width, height, thickness, font_scale) for text in texts]

        positions = []
        for text, (font, _) in zip(texts, fonts_and_emoji_fonts):
            bbox = ImageDraw.Draw(Image.new('RGB', (1, 1))).textbbox((0, 0), text, font=font)
            text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
            position = (
                (width // 2) + int(width * offset[0]) - (text_width // 2),
                (height // 2) + int(height * offset[1]) - (text_height // 2)
            )
            positions.append(position)

        with tempfile.NamedTemporaryFile(suffix='.yuv', delete=False) as raw_file:
            raw_path = raw_file.name

        cap = cv2.VideoCapture(input_path)
        frame_count = 0

        with open(raw_path, 'wb') as raw_out:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                for text, (font, emoji_font), position, start_time, end_time in zip(texts, fonts_and_emoji_fonts,
                                                                                    positions, start_times, end_times):
                    if start_time * fps <= frame_count <= end_time * fps:
                        frame = self._process_frame(frame, text, font, emoji_font, position, color, shadow_offset,
                                                    shadow_color,
                                                    outline, outline_color, outline_thickness)

                yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
                raw_out.write(yuv.tobytes())
                frame_count += 1

        cap.release()

        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as output_file:
            output_path = output_file.name

        ffmpeg_command = [
            'ffmpeg',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{width}x{height}',
            '-pix_fmt', 'yuv420p',
            '-r', str(fps),
            '-i', raw_path,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-y',
            output_path
        ]

        subprocess.run(ffmpeg_command, check=True)

        os.remove(raw_path)
        os.remove(input_path)
        print("Transcript added to video, original file updated!")
        return output_path