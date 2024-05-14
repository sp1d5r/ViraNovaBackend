import cv2
import numpy as np
from .bounding_box_interface import BoundingBoxGenerator

class GreedyBoundingBoxGenerator(BoundingBoxGenerator):
    def __init__(self, aspect_ratio=(9, 16)):
        self.aspect_ratio = aspect_ratio

    def generate_bounding_boxes(self, saliency_video_path):
        cap = cv2.VideoCapture(saliency_video_path)
        bounding_boxes = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            saliency_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            box = self._greedy_optimize_box(saliency_frame)
            bounding_boxes.append(box)
        cap.release()
        return bounding_boxes

    def _greedy_optimize_box(self, saliency_map):
        box = self._initialize_box(saliency_map)
        while True:
            new_box = self._expand_box(saliency_map, box)
            if new_box == box:  # No improvement
                break
            box = new_box
        return box

    def _initialize_box(self, saliency_map):
        y, x = np.unravel_index(np.argmax(saliency_map), saliency_map.shape)
        initial_width = int(saliency_map.shape[1] * 0.1)  # Start with 10% of the image width
        initial_height = int(initial_width * self.aspect_ratio[1] / self.aspect_ratio[0])
        x = max(0, min(x - initial_width // 2, saliency_map.shape[1] - initial_width))
        y = max(0, min(y - initial_height // 2, saliency_map.shape[0] - initial_height))
        return (x, y, initial_width, initial_height)

    def _expand_box(self, saliency_map, box):
        x, y, width, height = box
        # Calculate potential expansions while maintaining aspect ratio
        expansions = []
        if x + width < saliency_map.shape[1]:  # Expand right
            new_width = width + int(height * self.aspect_ratio[0] / self.aspect_ratio[1])
            if x + new_width <= saliency_map.shape[1]:
                expansions.append((x, y, new_width, height))
        if x > 0:  # Expand left
            new_width = width + int(height * self.aspect_ratio[0] / self.aspect_ratio[1])
            new_x = max(0, x - (new_width - width))
            if new_x < x:
                expansions.append((new_x, y, new_width, height))
        if y + height < saliency_map.shape[0]:  # Expand down
            new_height = height + int(width * self.aspect_ratio[1] / self.aspect_ratio[0])
            if y + new_height <= saliency_map.shape[0]:
                expansions.append((x, y, width, new_height))
        if y > 0:  # Expand up
            new_height = height + int(width * self.aspect_ratio[1] / self.aspect_ratio[0])
            new_y = max(0, y - (new_height - height))
            if new_y < y:
                expansions.append((x, new_y, width, new_height))

        # Choose the expansion that increases the saliency sum the most
        best_box = box
        max_saliency_increase = 0
        current_saliency_sum = np.sum(saliency_map[y:y+height, x:x+width])
        for exp in expansions:
            ex, ey, ew, eh = exp
            exp_saliency_sum = np.sum(saliency_map[ey:ey+eh, ex:ex+ew])
            if exp_saliency_sum - current_saliency_sum > max_saliency_increase:
                max_saliency_increase = exp_saliency_sum - current_saliency_sum
                best_box = exp
        return best_box

    def evaluate_saliency(self, saliency_video_path, bounding_boxes):
        cap = cv2.VideoCapture(saliency_video_path)
        results = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            saliency_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            for box in bounding_boxes:
                x, y, w, h = box
                crop = saliency_frame[y:y + h, x:x + w]
                saliency = np.mean(crop)
                results.append((box, saliency))
        cap.release()
        return results

    def crop_video(self, video_path, bounding_boxes, output_path):
        cap = cv2.VideoCapture(video_path)
        # Assume all bounding boxes are of equal size and the output frame should fit all horizontally
        frame_width = sum(box[2] for box in bounding_boxes)
        frame_height = max(box[3] for box in bounding_boxes)  # Use the height of the tallest box
        fourcc = cv2.VideoWriter_fourcc(*'avc1')  # Codec for H.264
        out = cv2.VideoWriter(output_path, fourcc, 20.0, (frame_width, frame_height), isColor=True)

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            stitched_frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)

            current_x = 0
            for x, y, w, h in bounding_boxes:
                cropped_frame = frame[y:y + h, x:x + w]
                # Resize cropped frame to match the tallest height in bounding boxes
                resized_cropped_frame = cv2.resize(cropped_frame, (w, frame_height), interpolation=cv2.INTER_AREA)
                stitched_frame[:, current_x:current_x + w] = resized_cropped_frame
                current_x += w

            out.write(stitched_frame)

        cap.release()
        out.release()
