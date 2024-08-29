import cv2
import numpy as np
from typing import Dict, List, Tuple, Callable
from scipy.interpolate import interp1d


class BoundingBoxGenerator:
    def __init__(self, step_size=10):
        self.step_size = step_size
        self.tiktok_aspect_ratio = 9 / 16  # TikTok aspect ratio (portrait mode)
        self.reaction_aspect_ratio = 16 / 9  # Reaction box aspect ratio
        self.half_screen_aspect_ratio = 9 / 8  # New half-screen box aspect ratio

    def _calculate_integral_image(self, frame):
        """Calculate the integral image of a given frame."""
        return cv2.integral(frame.astype(np.float32))

    def _saliency_captured(self, integral_image, x1, y1, x2, y2):
        """Calculate the saliency captured by a bounding box using the integral image."""
        return (integral_image[y2 + 1, x2 + 1] - integral_image[y1, x2 + 1] -
                integral_image[y2 + 1, x1] + integral_image[y1, x1])

    def _find_best_single_box(self, integral_image, aspect_ratio):
        """Find the best single bounding box that maximizes the saliency captured."""
        height, width = integral_image.shape[:2]
        height -= 1  # Adjust for integral image size
        width -= 1  # Adjust for integral image size
        best_box = (0, 0, 0, 0)
        best_saliency = 0

        for h in range(self.step_size, height, self.step_size):
            w = int(h * aspect_ratio)
            if w > width:
                break

            for y in range(0, height - h + 1, self.step_size):
                for x in range(0, width - w + 1, self.step_size):
                    saliency = self._saliency_captured(integral_image, x, y, x + w - 1, y + h - 1)

                    if saliency > best_saliency:
                        best_saliency = saliency
                        best_box = (x, y, w, h)

        return best_box

    def _find_best_reaction_box(self, integral_image):
        height, width = integral_image.shape[:2]
        height -= 1  # Adjust for integral image size
        width -= 1  # Adjust for integral image size
        max_height = height // 2  # Maximum height is 50% of the screen
        max_width = width // 2  # Maximum width is 50% of the screen

        # Define starting points (x, y) for each edge
        start_points = [
            (0, height // 2),  # Left edge
            (width // 2, 0),  # Top edge
            (width // 2, 0),  # Right edge
            (0, height // 2)  # Bottom edge
        ]

        best_box = None
        best_saliency_ratio = 0

        for start_x, start_y in start_points:
            current_height = max_height
            while current_height > self.step_size:
                current_width = int(current_height * self.reaction_aspect_ratio)
                if current_width > max_width:
                    current_width = max_width
                    current_height = int(current_width / self.reaction_aspect_ratio)

                # Adjust x and y to keep the box within frame boundaries
                x = min(start_x, width - current_width)
                y = min(start_y, height - current_height)

                saliency = self._saliency_captured(integral_image, x, y,
                                                   x + current_width - 1, y + current_height - 1)
                area = current_width * current_height
                saliency_ratio = saliency / area

                if saliency_ratio > best_saliency_ratio:
                    best_saliency_ratio = saliency_ratio
                    best_box = (x, y, current_width, current_height)

                # Check for significant drop in saliency
                smaller_height = current_height - self.step_size
                smaller_width = int(smaller_height * self.reaction_aspect_ratio)
                smaller_saliency = self._saliency_captured(integral_image, x, y,
                                                           x + smaller_width - 1, y + smaller_height - 1)
                smaller_area = smaller_width * smaller_height
                smaller_saliency_ratio = smaller_saliency / smaller_area

                if smaller_saliency_ratio < saliency_ratio * 0.9:  # 10% drop in saliency ratio
                    break

                current_height -= self.step_size

        return best_box

    def _find_best_two_boxes(self, integral_image):
        """Find the best two bounding boxes that maximize the saliency captured."""
        height, width = integral_image.shape[:2]
        height -= 1  # Adjust for integral image size
        width -= 1  # Adjust for integral image size
        best_boxes = [(0, 0, 0, 0), (0, 0, 0, 0)]
        best_saliency = 0

        # Calculate dimensions for two boxes that evenly split the screen
        box_width = width // 2
        box_height = height

        for y in range(0, height - box_height + 1, self.step_size):
            saliency1 = self._saliency_captured(integral_image, 0, y, box_width - 1, y + box_height - 1)
            saliency2 = self._saliency_captured(integral_image, box_width, y, width - 1, y + box_height - 1)
            total_saliency = saliency1 + saliency2

            if total_saliency > best_saliency:
                best_saliency = total_saliency
                best_boxes = [(0, y, box_width, box_height), (box_width, y, box_width, box_height)]

        return best_boxes

    def _find_best_half_screen_box(self, integral_image):
        """Find the best half-screen box that maximizes the saliency captured."""
        height, width = integral_image.shape[:2]
        height -= 1  # Adjust for integral image size
        width -= 1  # Adjust for integral image size

        # The height of the box should be half of the frame height
        box_height = height
        box_width = int(box_height * self.half_screen_aspect_ratio)

        best_box = (0, 0, 0, 0)
        best_saliency = 0

        for x in range(0, width - box_width + 1, self.step_size):
            saliency = self._saliency_captured(integral_image, x, 0, x + box_width - 1, box_height - 1)

            if saliency > best_saliency:
                best_saliency = saliency
                best_box = (x, 0, box_width, box_height)

        return best_box

    def get_total_frames(self, video_path):
        """Get the total number of frames in the video."""
        video = cv2.VideoCapture(video_path)
        if not video.isOpened():
            print("Error: Unable to open video file.")
            return 0

        total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        video.release()
        return total_frames

    def generate_bounding_boxes(self, saliency_video_path, update_progress, skip_frames=2):
        saliency_video = cv2.VideoCapture(saliency_video_path)
        if not saliency_video.isOpened():
            print("Error: Unable to open saliency video file.")
            return {}

        total_frames = int(saliency_video.get(cv2.CAP_PROP_FRAME_COUNT))
        print(f"Total frames in the video: {total_frames}")

        bounding_boxes = {
            "standard_tiktok": [],
            "two_boxes": [],
            "reaction_box": [],
            "half_screen_box": []
        }
        frame_count = 0

        while True:
            success, frame = saliency_video.read()
            if not success:
                break

            try:
                gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                integral_image = self._calculate_integral_image(gray_frame)

                bounding_boxes["standard_tiktok"].append(
                    self._find_best_single_box(integral_image, self.tiktok_aspect_ratio))
                bounding_boxes["two_boxes"].append(self._find_best_two_boxes(integral_image))
                bounding_boxes["reaction_box"].append(self._find_best_reaction_box(integral_image))
                bounding_boxes["half_screen_box"].append(
                    self._find_best_half_screen_box(integral_image)
                )

                if frame_count % 100 == 0:
                    progress = (frame_count / total_frames) * 100
                    update_progress(progress)
                    print(f"Processed {frame_count}/{total_frames} frames")
            except Exception as e:
                print(f"Error processing frame {frame_count}: {str(e)}")
                break

            frame_count += 1

        saliency_video.release()
        print(f"Total frames processed: {frame_count}/{total_frames}")

        # Adjust total_frames to account for skipped frames
        total_frames_with_skips = total_frames * (skip_frames + 1)

        interpolated_boxes = self._interpolate_bounding_boxes(bounding_boxes, total_frames_with_skips, skip_frames)
        print("Interpolated Boxes.")
        return interpolated_boxes

    def _interpolate_bounding_boxes(self, bounding_boxes, total_frames, skip_frames):
        interpolated_boxes = {}

        for box_type, boxes in bounding_boxes.items():
            if box_type == "two_boxes":
                interpolated_boxes[box_type] = self._interpolate_two_boxes(boxes, total_frames, skip_frames)
            else:
                interpolated_boxes[box_type] = self._interpolate_single_box(boxes, total_frames, skip_frames)

        return interpolated_boxes

    def _interpolate_single_box(self, boxes, total_frames, skip_frames):
        processed_frames = len(boxes)
        frame_indices = np.arange(0, processed_frames * (skip_frames + 1), skip_frames + 1)

        if not boxes:
            return [None] * total_frames

        boxes_array = np.array(boxes)

        interpolate_func = interp1d(frame_indices, boxes_array.T, kind='linear', axis=1, bounds_error=False,
                                    fill_value="extrapolate")

        all_frame_indices = np.arange(total_frames)
        interpolated = interpolate_func(all_frame_indices).T

        return [tuple(map(int, box)) for box in interpolated]

    def _interpolate_two_boxes(self, boxes, total_frames, skip_frames):
        processed_frames = len(boxes)
        frame_indices = np.arange(0, processed_frames * (skip_frames + 1), skip_frames + 1)

        if not boxes:
            return [None] * total_frames

        boxes_array = np.array([list(box1) + list(box2) for box1, box2 in boxes])

        interpolate_func = interp1d(frame_indices, boxes_array.T, kind='linear', axis=1, bounds_error=False,
                                    fill_value="extrapolate")

        all_frame_indices = np.arange(total_frames)
        interpolated = interpolate_func(all_frame_indices).T

        return [(tuple(map(int, box[:4])), tuple(map(int, box[4:]))) for box in interpolated]

    def smooth_bounding_boxes(self, bboxes, window_size=3):
        smoothed_boxes = []
        for i in range(len(bboxes)):
            if bboxes[i] is None:
                smoothed_boxes.append(None)
                continue

            x1, y1, w, h = 0, 0, 0, 0
            count = 0
            for j in range(max(0, i - window_size // 2), min(len(bboxes), i + window_size // 2 + 1)):
                if bboxes[j] is not None:
                    x1 += bboxes[j][0]
                    y1 += bboxes[j][1]
                    w += bboxes[j][2]
                    h += bboxes[j][3]
                    count += 1
            if count > 0:
                smoothed_boxes.append((x1 // count, y1 // count, w // count, h // count))
            else:
                smoothed_boxes.append(None)
        return smoothed_boxes
