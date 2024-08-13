import cv2
import numpy as np
from typing import List, Tuple, Dict
import tempfile
import os

class VideoCropper:
    def __init__(self, input_video_path: str, bounding_boxes: Dict[str, List[Tuple[int, int, int, int]]],
                 frame_types: List[str], skip_frames: int = 0):
        self.input_video_path = input_video_path
        self.bounding_boxes = bounding_boxes
        self.frame_types = frame_types
        self.skip_frames = skip_frames
        self.video = None
        self.fps = None
        self.total_frames = None
        self.width = None
        self.height = None
        self.target_height = 1920  # TikTok video height
        self.target_width = 1080  # TikTok video width
        self.previous_reaction_box = None

    def _initialize_video(self):
        self.video = cv2.VideoCapture(self.input_video_path)
        if not self.video.isOpened():
            raise ValueError("Error: Unable to open input video file.")
        self.fps = int(self.video.get(cv2.CAP_PROP_FPS))
        self.total_frames = int(self.video.get(cv2.CAP_PROP_FRAME_COUNT))
        self.width = int(self.video.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.video.get(cv2.CAP_PROP_FRAME_HEIGHT))

    def _get_bounding_box(self, frame_idx: int) -> Tuple[str, List[Tuple[int, int, int, int]]]:
        bb_idx = frame_idx // (self.skip_frames + 1)
        if bb_idx >= len(self.frame_types):
            bb_idx = len(self.frame_types) - 1
        frame_type = self.frame_types[bb_idx]

        if frame_type == "standard_tiktok":
            return frame_type, [self.bounding_boxes["standard_tiktok"][bb_idx]]
        elif frame_type in ["two_boxes", "two_boxes_reversed"]:
            return frame_type, self.bounding_boxes["two_boxes"][bb_idx]
        elif frame_type == "picture_in_picture":
            return frame_type, [self.bounding_boxes["standard_tiktok"][bb_idx]]
        elif frame_type == "reaction_box":
            main_box = self.bounding_boxes["standard_tiktok"][bb_idx]
            reaction_box = self.bounding_boxes["reaction_box"][bb_idx]
            if reaction_box is None and self.previous_reaction_box is not None:
                reaction_box = self.previous_reaction_box
            if reaction_box is not None:
                self.previous_reaction_box = reaction_box
            return frame_type, [main_box, reaction_box]
        else:
            raise ValueError(f"Unknown frame type: {frame_type}")

    def _process_standard_tiktok(self, frame: np.ndarray, box: Tuple[int, int, int, int]) -> np.ndarray:
        try:
            x, y, w, h = box
            cropped_frame = frame[y:y + h, x:x + w]
            if cropped_frame.size == 0:
                raise ValueError("Cropped frame is empty")
            return cv2.resize(cropped_frame, (self.target_width, self.target_height))
        except Exception as e:
            print(f"Error in _process_standard_tiktok: {str(e)}")
            return None

    def _process_two_boxes(self, frame: np.ndarray, boxes: List[Tuple[int, int, int, int]], vertical: bool = True,
                           reverse: bool = False) -> np.ndarray:
        try:
            cropped_frames = [frame[y:y + h, x:x + w] for x, y, w, h in boxes]
            if reverse:
                cropped_frames = cropped_frames[::-1]

            resized_frames = [cv2.resize(frame, (self.target_width, self.target_height // 2)) for frame in cropped_frames]

            if vertical:
                stacked_frame = np.vstack(resized_frames)
            else:
                stacked_frame = np.hstack(resized_frames)

            return stacked_frame
        except Exception as e:
            print(f"Error in _process_two_boxes: {str(e)}")
            return None

    def _process_picture_in_picture(self, frame: np.ndarray, box: Tuple[int, int, int, int]) -> np.ndarray:
        try:
            # Process the main (background) frame
            main_frame = self._process_standard_tiktok(frame, box)
            if main_frame is None:
                return None

            # Create a smaller version of the original frame for PiP
            pip_height = self.target_height // 4  # 1/4 of the frame height
            pip_width = int(pip_height * (self.width / self.height))  # Maintain aspect ratio

            # Add padding for border
            border_thickness = 3
            padding = border_thickness * 2
            pip_frame = cv2.resize(frame, (pip_width - padding, pip_height - padding))

            # Create a transparent frame for the PiP with border
            pip_with_border = np.zeros((pip_height, pip_width, 4), dtype=np.uint8)

            # Draw white border
            cv2.rectangle(pip_with_border, (0, 0), (pip_width - 1, pip_height - 1), (255, 255, 255, 255), border_thickness)

            # Place the PiP frame inside the border
            pip_with_border[border_thickness:pip_height - border_thickness,
            border_thickness:pip_width - border_thickness, :3] = pip_frame
            pip_with_border[border_thickness:pip_height - border_thickness,
            border_thickness:pip_width - border_thickness, 3] = 255

            # Calculate position for PiP (centered at the bottom)
            y_offset = self.target_height - pip_height - 20  # 20 pixels from bottom
            x_offset = (self.target_width - pip_width) // 2

            # Overlay PiP on main frame
            for c in range(0, 3):
                alpha = pip_with_border[:, :, 3] / 255.0
                main_frame[y_offset:y_offset + pip_height, x_offset:x_offset + pip_width, c] = \
                    (1 - alpha) * main_frame[y_offset:y_offset + pip_height, x_offset:x_offset + pip_width, c] + \
                    alpha * pip_with_border[:, :, c]

            return main_frame
        except Exception as e:
            print(f"Error in _process_picture_in_picture: {str(e)}")
            return None

    def _process_reaction_box(self, frame: np.ndarray, boxes: List[Tuple[int, int, int, int]]) -> np.ndarray:
        try:
            main_box, reaction_box = boxes
            # Process the main (background) frame
            main_frame = self._process_standard_tiktok(frame, main_box)
            if main_frame is None:
                return None

            if reaction_box is None:
                return main_frame

            # Create a smaller version of the reaction area
            x, y, w, h = reaction_box
            reaction_frame = frame[y:y + h, x:x + w]
            reaction_height = self.target_height // 4  # 1/4 of the frame height
            reaction_width = int(reaction_height * (w / h))  # Maintain aspect ratio

            # Add padding for border
            border_thickness = 3
            padding = border_thickness * 2
            reaction_frame = cv2.resize(reaction_frame, (reaction_width - padding, reaction_height - padding))

            # Create a transparent frame for the reaction box with border
            reaction_with_border = np.zeros((reaction_height, reaction_width, 4), dtype=np.uint8)

            # Draw white border
            cv2.rectangle(reaction_with_border, (0, 0), (reaction_width - 1, reaction_height - 1), (255, 255, 255, 255), border_thickness)

            # Place the reaction frame inside the border
            reaction_with_border[border_thickness:reaction_height - border_thickness,
            border_thickness:reaction_width - border_thickness, :3] = reaction_frame
            reaction_with_border[border_thickness:reaction_height - border_thickness,
            border_thickness:reaction_width - border_thickness, 3] = 255

            # Calculate position for reaction box (centered at the bottom)
            y_offset = self.target_height - reaction_height - 20  # 20 pixels from bottom
            x_offset = (self.target_width - reaction_width) // 2

            # Overlay reaction box on main frame
            for c in range(0, 3):
                alpha = reaction_with_border[:, :, 3] / 255.0
                main_frame[y_offset:y_offset + reaction_height, x_offset:x_offset + reaction_width, c] = \
                    (1 - alpha) * main_frame[y_offset:y_offset + reaction_height, x_offset:x_offset + reaction_width, c] + \
                    alpha * reaction_with_border[:, :, c]

            return main_frame
        except Exception as e:
            print(f"Error in _process_reaction_box: {str(e)}")
            return None

    def crop_video(self) -> str:
        self._initialize_video()

        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_file:
            output_path = tmp_file.name

        fourcc = cv2.VideoWriter_fourcc(*'avc1')
        out = cv2.VideoWriter(output_path, fourcc, self.fps, (self.target_width, self.target_height))

        frame_idx = 0
        while True:
            ret, frame = self.video.read()
            if not ret:
                break

            if frame is None or frame.size == 0:
                print(f"Empty or invalid frame at index {frame_idx}. Skipping...")
                frame_idx += 1
                continue

            frame_type, boxes = self._get_bounding_box(frame_idx)

            processed_frame = None
            if frame_type == "standard_tiktok":
                processed_frame = self._process_standard_tiktok(frame, boxes[0])
            elif frame_type == "two_boxes":
                processed_frame = self._process_two_boxes(frame, boxes, vertical=True)
            elif frame_type == "two_boxes_reversed":
                processed_frame = self._process_two_boxes(frame, boxes, vertical=True, reverse=True)
            elif frame_type == "picture_in_picture":
                processed_frame = self._process_picture_in_picture(frame, boxes[0])
            elif frame_type == "reaction_box":
                processed_frame = self._process_reaction_box(frame, boxes)
            else:
                print(f"Unknown frame type: {frame_type}. Skipping...")

            if processed_frame is not None:
                out.write(processed_frame)
            else:
                print(f"Failed to process frame {frame_idx}. Skipping...")

            frame_idx += 1
            if frame_idx % 100 == 0:
                print(f"Processed {frame_idx}/{self.total_frames} frames")

        self.video.release()
        out.release()
        print(f"Cropped video saved to: {output_path}")
        return output_path

    def clean_up(self, temp_file_path: str):
        try:
            os.remove(temp_file_path)
            print(f"Temporary file {temp_file_path} has been removed.")
        except Exception as e:
            print(f"Error removing temporary file {temp_file_path}: {str(e)}")