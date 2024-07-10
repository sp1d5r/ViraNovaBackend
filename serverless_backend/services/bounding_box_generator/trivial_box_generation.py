from .bounding_box_interface import BoundingBoxGenerator
import cv2
import numpy as np


class TrivialBoundingBoxGenerator(BoundingBoxGenerator):
    def __init__(self, aspect_ratio=(9, 15)):
        self.aspect_ratio = aspect_ratio


    def generate_bounding_boxes(self, saliency_video_path):
        cap = cv2.VideoCapture(saliency_video_path)
        average_saliency_map = self._compute_average_saliency_map(cap)
        cap.release()
        initial_box = self._find_initial_box(average_saliency_map)
        optimized_box = self._optimize_box(average_saliency_map, initial_box)
        return [optimized_box]

    def _compute_average_saliency_map(self, cap):
        frame_count = 0
        average_saliency_map = None

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            saliency_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if average_saliency_map is None:
                average_saliency_map = np.zeros_like(saliency_frame, dtype=np.float32)
            average_saliency_map += saliency_frame
            frame_count += 1

        if frame_count > 0:
            average_saliency_map /= frame_count
        return average_saliency_map.astype(np.uint8)

    def _find_initial_box(self, saliency_map):
        height, width = saliency_map.shape
        desired_aspect_ratio = self.aspect_ratio[0] / self.aspect_ratio[1]
        box_width = min(width, int(height * desired_aspect_ratio))
        box_height = min(height, int(box_width / desired_aspect_ratio))
        x = (width - box_width) // 2
        y = (height - box_height) // 2
        return (x, y, box_width, box_height)

    def _optimize_box(self, saliency_map, initial_box):
        x, y, w, h = initial_box
        max_saliency = -1
        best_box = None
        step_size = 10
        for nx in range(max(0, x - step_size), min(saliency_map.shape[1] - w, x + step_size) + 1, step_size):
            for ny in range(max(0, y - step_size), min(saliency_map.shape[0] - h, y + step_size) + 1, step_size):
                crop = saliency_map[ny:ny + h, nx:nx + w]
                saliency = np.mean(crop)
                if saliency > max_saliency:
                    max_saliency = saliency
                    best_box = (nx, ny, w, h)
        return best_box if best_box else initial_box

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
                crop = saliency_frame[y:y+h, x:x+w]
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
                cropped_frame = frame[y:y+h, x:x+w]
                # Resize cropped frame to match the tallest height in bounding boxes
                resized_cropped_frame = cv2.resize(cropped_frame, (w, frame_height), interpolation=cv2.INTER_AREA)
                stitched_frame[:, current_x:current_x+w] = resized_cropped_frame
                current_x += w

            out.write(stitched_frame)

        cap.release()
        out.release()

