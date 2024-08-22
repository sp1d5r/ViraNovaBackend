import cv2
import os
import tempfile
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import subprocess


class AddTextToVideoService:
    def __init__(self):
        self.font_base_path = 'serverless_backend/assets/fonts'
        self.static_overlay = None

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

    def _get_font(self, text, max_width, max_height, thickness, font_scale):
        font_path = os.path.abspath(os.path.join(self.font_base_path, f'Montserrat-{thickness}.ttf'))
        if not os.path.exists(font_path):
            raise FileNotFoundError(f"Error: Font file not found at {font_path}")

        font_size = int(font_scale * 20)
        font = ImageFont.truetype(font_path, font_size)

        while True:
            bbox = ImageDraw.Draw(Image.new('RGB', (1, 1))).textbbox((0, 0), text, font=font)
            if bbox[2] - bbox[0] <= max_width and bbox[3] - bbox[1] <= max_height:
                break
            font_size -= 1
            if font_size <= 0:
                raise ValueError("Error: Text is too large to fit in the video")
            font = ImageFont.truetype(font_path, font_size)

        return font

    def _create_static_overlay(self, width, height, static_additions):
        overlay = Image.new('RGBA', (width, height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)

        for addition in static_additions:
            text = addition['text']
            font = addition['font']
            position = addition['position']
            color = addition['color']
            shadow_offset = addition['shadow_offset']
            shadow_color = addition['shadow_color']
            outline = addition['outline']
            outline_color = addition['outline_color']
            outline_thickness = addition['outline_thickness']

            # Draw shadow
            draw.text((position[0] + shadow_offset[0], position[1] + shadow_offset[1]), text, font=font, fill=shadow_color)

            # Draw outline
            if outline:
                for x in range(-outline_thickness, outline_thickness + 1):
                    for y in range(-outline_thickness, outline_thickness + 1):
                        if x != 0 or y != 0:
                            draw.text((position[0] + x, position[1] + y), text, font=font, fill=outline_color)

            # Draw main text
            draw.text(position, text, font=font, fill=color)

        return np.array(overlay)

    def _process_frame(self, frame, dynamic_additions):
        # Apply static overlay
        if self.static_overlay is not None:
            alpha_channel = self.static_overlay[:, :, 3] / 255.0
            for c in range(3):
                frame[:, :, c] = frame[:, :, c] * (1 - alpha_channel) + self.static_overlay[:, :, c] * alpha_channel

        # Process dynamic additions (e.g., transcript)
        if dynamic_additions:
            overlay = Image.new('RGBA', (frame.shape[1], frame.shape[0]), (255, 255, 255, 0))
            draw = ImageDraw.Draw(overlay)

            for addition in dynamic_additions:
                text = addition['text']
                font = addition['font']
                position = addition['position']
                color = addition['color']
                shadow_offset = addition['shadow_offset']
                shadow_color = addition['shadow_color']
                outline = addition['outline']
                outline_color = addition['outline_color']
                outline_thickness = addition['outline_thickness']

                # Draw shadow
                draw.text((position[0] + shadow_offset[0], position[1] + shadow_offset[1]), text, font=font, fill=shadow_color)

                # Draw outline
                if outline:
                    for x in range(-outline_thickness, outline_thickness + 1):
                        for y in range(-outline_thickness, outline_thickness + 1):
                            if x != 0 or y != 0:
                                draw.text((position[0] + x, position[1] + y), text, font=font, fill=outline_color)

                # Draw main text
                draw.text(position, text, font=font, fill=color)

            # Convert the overlay to numpy array and merge with the frame
            overlay_array = np.array(overlay)
            alpha_channel = overlay_array[:, :, 3] / 255.0
            for c in range(3):
                frame[:, :, c] = frame[:, :, c] * (1 - alpha_channel) + overlay_array[:, :, c] * alpha_channel

        return frame

    def process_video_with_text(self, input_path, text_additions):
        fps, width, height, total_frames = self._get_video_info(input_path)

        # Separate static and dynamic additions
        static_additions = []
        dynamic_additions = []
        for addition in text_additions:
            if addition.get('type') == 'transcript':
                dynamic_additions.extend(self._prepare_transcript(addition, width, height, fps))
            elif addition.get('static', True):  # Assume static unless specified otherwise
                static_additions.append(self._prepare_text_addition(addition, width, height))
            else:
                dynamic_additions.append(self._prepare_text_addition(addition, width, height))

        # Create static overlay
        self.static_overlay = self._create_static_overlay(width, height, static_additions)

        with tempfile.NamedTemporaryFile(suffix='.yuv', delete=False) as raw_file:
            raw_path = raw_file.name

        cap = cv2.VideoCapture(input_path)
        frame_count = 0

        with open(raw_path, 'wb') as raw_out:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                current_additions = [
                    addition for addition in dynamic_additions
                    if addition['start_frame'] <= frame_count <= addition['end_frame']
                ]

                frame = self._process_frame(frame, current_additions)

                yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
                raw_out.write(yuv.tobytes())
                frame_count += 1

                # Optional: Print progress
                if frame_count % 100 == 0:
                    print(f"Processed {frame_count}/{total_frames} frames")

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
        print("All text additions applied to video, original file updated!")
        return output_path

    def _prepare_text_addition(self, addition, width, height):
        font = self._get_font(addition['text'], width, height, addition['thickness'], addition['font_scale'])
        bbox = ImageDraw.Draw(Image.new('RGB', (1, 1))).textbbox((0, 0), addition['text'], font=font)
        text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]

        if 'position' in addition:
            position = addition['position']
        else:
            position = ((width - text_width) // 2, (height - text_height) // 2)

        if 'offset' in addition:
            position = (
                position[0] + int(width * addition['offset'][0]),
                position[1] + int(height * addition['offset'][1])
            )

        return {
            'text': addition['text'],
            'font': font,
            'position': position,
            'color': addition['color'],
            'shadow_offset': addition.get('shadow_offset', (2, 2)),
            'shadow_color': addition.get('shadow_color', (0, 0, 0)),
            'outline': addition.get('outline', False),
            'outline_color': addition.get('outline_color', (0, 0, 0)),
            'outline_thickness': addition.get('outline_thickness', 2),
            'start_frame': 0,
            'end_frame': float('inf')
        }

    def _prepare_transcript(self, transcript, width, height, fps):
        prepared_lines = []

        for text, start_time, end_time in zip(transcript['texts'], transcript['start_times'], transcript['end_times']):
            font = self._get_font(text, width, height, transcript['thickness'], transcript['font_scale'])
            bbox = ImageDraw.Draw(Image.new('RGB', (1, 1))).textbbox((0, 0), text, font=font)
            text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]

            position = (
                (width // 2) + int(width * transcript['offset'][0]) - (text_width // 2),
                (height // 2) + int(height * transcript['offset'][1]) - (text_height // 2)
            )

            prepared_lines.append({
                'text': text,
                'font': font,
                'position': position,
                'color': transcript['color'],
                'shadow_offset': transcript.get('shadow_offset', (2, 2)),
                'shadow_color': transcript.get('shadow_color', (0, 0, 0)),
                'outline': transcript.get('outline', False),
                'outline_color': transcript.get('outline_color', (0, 0, 0)),
                'outline_thickness': transcript.get('outline_thickness', 2),
                'start_frame': int(start_time * fps),
                'end_frame': int(end_time * fps)
            })

        return prepared_lines
