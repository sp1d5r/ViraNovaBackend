import cv2
import os
import tempfile
from PIL import Image, ImageDraw, ImageFont
import numpy as np

class AddTextToVideoService:
    def resize_video(self, input_path, output_path, target_width, target_height):
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            print("Error: Could not open video.")
            return None

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Calculate the aspect ratio and determine the new dimensions
        aspect_ratio = width / height
        if width > height:
            new_width = target_width
            new_height = int(target_width / aspect_ratio)
        else:
            new_height = target_height
            new_width = int(target_height * aspect_ratio)

        out = cv2.VideoWriter(output_path, fourcc, fps, (new_width, new_height))

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            resized_frame = cv2.resize(frame, (new_width, new_height))
            out.write(resized_frame)

        cap.release()
        out.release()

    def add_text_centered(self, input_path, text, font_scale, position=None, color=(255, 255, 255), thickness='Bold', shadow_offset=(2,2), shadow_color=(0,0,0), outline=False, outline_color=(0, 0, 0), outline_thickness=2, offset=None, start_seconds=None, end_seconds=None):
        return self.add_text(input_path, text, font_scale, position, color, thickness, start_seconds, end_seconds, shadow_offset, shadow_color, outline, outline_color, outline_thickness, offset)

    def add_text(self, input_path, text, font_scale, position, color, thickness, start_seconds=None, end_seconds=None, shadow_offset=(2,2), shadow_color=(0,0,0), outline=False, outline_color=(0,0,0), outline_thickness=2, offset=None):
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            print("Error: Could not open video.")
            return None

        fps = cap.get(cv2.CAP_PROP_FPS)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Temporary resized video path
        _, resized_video_path = tempfile.mkstemp(suffix='.mp4')
        self.resize_video(input_path, resized_video_path, 720, 1280)  # Resize to 720x1280

        # Open the resized video
        cap = cv2.VideoCapture(resized_video_path)
        if not cap.isOpened():
            print("Error: Could not open resized video.")
            return None

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        _, temp_output_path = tempfile.mkstemp(suffix='.mp4')  # Create a temporary file
        out = cv2.VideoWriter(temp_output_path, fourcc, fps, (width, height))
        current_frame = 0

        # Load the custom font
        font_relative_path = f'assets/fonts/Montserrat-{thickness}.ttf'
        font_absolute_path = os.path.abspath(font_relative_path)

        if not os.path.exists(font_absolute_path):
            print(f"Error: Font file not found at {font_absolute_path}")
            return None

        def calculate_font_size(text, width, height, font_path):
            font_size = int(font_scale * 20)
            font = ImageFont.truetype(font_path, font_size)
            text_bbox = ImageDraw.Draw(Image.new('RGB', (width, height))).textbbox((0, 0), text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]

            while text_width > width or text_height > height:
                font_size -= 1
                font = ImageFont.truetype(font_path, font_size)
                text_bbox = ImageDraw.Draw(Image.new('RGB', (width, height))).textbbox((0, 0), text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]

            return font

        font = calculate_font_size(text, width, height, font_absolute_path)

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Convert frame to PIL image
            pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_image)

            text_bbox = draw.textbbox((0, 0), text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]

            if offset is not None:
                # Calculate the position based on the offset
                position = (
                    (width // 2) + int(width * offset[0]) - (text_width // 2),
                    (height // 2) + int(height * offset[1]) - (text_height // 2)
                )

            if position is None:
                position = (50, 50)  # Default position if none is provided

            if start_seconds is not None and end_seconds is not None:
                # Only add text between specified seconds
                if start_seconds * fps <= current_frame <= end_seconds * fps:
                    # Draw shadow
                    draw.text((position[0] + shadow_offset[0], position[1] + shadow_offset[1]), text, font=font, fill=shadow_color)

                    # Draw outline (stroke)
                    if outline:
                        for x in range(-outline_thickness, outline_thickness + 1):
                            for y in range(-outline_thickness, outline_thickness + 1):
                                if x != 0 or y != 0:
                                    draw.text((position[0] + x, position[1] + y), text, font=font, fill=outline_color)

                    # Draw main text
                    draw.text(position, text, font=font, fill=color)
            else:
                # Add text to all frames
                # Draw shadow
                draw.text((position[0] + shadow_offset[0], position[1] + shadow_offset[1]), text, font=font, fill=shadow_color)

                # Draw outline (stroke)
                if outline:
                    for x in range(-outline_thickness, outline_thickness + 1):
                        for y in range(-outline_thickness, outline_thickness + 1):
                            if x != 0 or y != 0:
                                draw.text((position[0] + x, position[1] + y), text, font=font, fill=outline_color)

                # Draw main text
                draw.text(position, text, font=font, fill=color)

            # Convert PIL image back to OpenCV format
            frame = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            out.write(frame)
            current_frame += 1

        # Release everything when done
        cap.release()
        out.release()

        os.remove(resized_video_path)  # Remove the temporary resized video
        os.remove(input_path)  # Remove the original input video
        print("Text added to video, original file updated!")
        return temp_output_path  # Return the path of the updated file

    def add_transcript(self, input_path, texts, start_times, end_times, font_scale=1, color=(255, 255, 255),
                       thickness='Bold', shadow_offset=(2, 2), shadow_color=(0, 0, 0), outline=False,
                       outline_color=(0, 0, 0), outline_thickness=2, offset=(0, 0)):
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            print("Error: Could not open video.")
            return None

        fps = cap.get(cv2.CAP_PROP_FPS)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Temporary resized video path
        _, resized_video_path = tempfile.mkstemp(suffix='.mp4')
        self.resize_video(input_path, resized_video_path, 720, 1280)  # Resize to 1280x720

        # Open the resized video
        cap = cv2.VideoCapture(resized_video_path)
        if not cap.isOpened():
            print("Error: Could not open resized video.")
            return None

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        _, temp_output_path = tempfile.mkstemp(suffix='.mp4')  # Create a temporary file
        out = cv2.VideoWriter(temp_output_path, fourcc, fps, (width, height))
        current_frame = 0

        # Load the custom font
        font_relative_path = f'assets/fonts/Montserrat-{thickness}.ttf'
        font_absolute_path = os.path.abspath(font_relative_path)

        if not os.path.exists(font_absolute_path):
            print(f"Error: Font file not found at {font_absolute_path}")
            return None

        def calculate_font_size(text, width, height, font_path):
            font_size = int(font_scale * 20)
            font = ImageFont.truetype(font_path, font_size)
            text_bbox = ImageDraw.Draw(Image.new('RGB', (width, height))).textbbox((0, 0), text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]

            while text_width > width or text_height > height:
                font_size -= 1
                font = ImageFont.truetype(font_path, font_size)
                text_bbox = ImageDraw.Draw(Image.new('RGB', (width, height))).textbbox((0, 0), text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]

            return font

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Convert frame to PIL image
            pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_image)

            for text, start_time, end_time in zip(texts, start_times, end_times):
                font = calculate_font_size(text, width, height, font_absolute_path)
                text_bbox = draw.textbbox((0, 0), text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]

                if offset is not None:
                    # Calculate the position based on the offset
                    position = (
                        (width // 2) + int(width * offset[0]) - (text_width // 2),
                        (height // 2) + int(height * offset[1]) - (text_height // 2)
                    )

                if position is None:
                    position = (50, 50)  # Default position if none is provided

                # Only add text between specified seconds
                if start_time * fps <= current_frame <= end_time * fps:
                    # Draw shadow
                    draw.text((position[0] + shadow_offset[0], position[1] + shadow_offset[1]), text, font=font,
                              fill=shadow_color)

                    # Draw outline (stroke)
                    if outline:
                        for x in range(-outline_thickness, outline_thickness + 1):
                            for y in range(-outline_thickness, outline_thickness + 1):
                                if x != 0 or y != 0:
                                    draw.text((position[0] + x, position[1] + y), text, font=font, fill=outline_color)

                    # Draw main text
                    draw.text(position, text, font=font, fill=color)

            # Convert PIL image back to OpenCV format
            frame = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            out.write(frame)
            current_frame += 1

        # Release everything when done
        cap.release()
        out.release()

        os.remove(resized_video_path)  # Remove the temporary resized video
        os.remove(input_path)  # Remove the original input video
        print("Transcript added to video, original file updated!")
        return temp_output_path  # Return the path of the updated file