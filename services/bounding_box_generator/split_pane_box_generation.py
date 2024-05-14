import cv2
import numpy as np
from .bounding_box_interface import BoundingBoxGenerator
from scipy.interpolate import interp1d
import moviepy.editor as mp


class SplitPaneBoxGenerator(BoundingBoxGenerator):
    def __init__(self, step_size=10):
        self.step_size = step_size

    def _saliency_captured(self, bb_height, bb_width, x, y, saliency_frame):
        """
        Calculate the saliency captured by a bounding box starting from position (x, y) in the saliency frame.

        Args:
        - bb_height: Height of the bounding box.
        - bb_width: Width of the bounding box.
        - x: Starting x-coordinate of the bounding box.
        - y: Starting y-coordinate of the bounding box.
        - saliency_frame: Saliency map frame.

        Returns:
        - saliency: Total saliency captured by the bounding box.
        """

        # Extract the region of interest (ROI) from the saliency frame
        roi = saliency_frame[y:y + bb_height, x:x + bb_width]

        # Calculate the total saliency captured by the bounding box
        total_saliency = np.sum(roi)

        return total_saliency

    def find_best_pos(self, bb_height, bb_width, saliency_frame, step_size=10):
        """
        Find the best position of the bounding box that maximizes the saliency captured by a bounding box of given dimensions.

        Args:
        - bb_height: Height of the bounding box.
        - bb_width: Width of the bounding box.
        - saliency_frame: Saliency map frame.
        - step_size: Step size for sliding the bounding box along the x-axis.

        Returns:
        - bb_x: x-position of the bounding box with maximum saliency.
        - bb_y: y-position of the bounding box (always 0).
        - bb_width: Width of the bounding box.
        - bb_height: Height of the bounding box.
        """

        max_saliency = 0
        max_x = 0
        max_y = 0  # Updated to allow for variable y-position

        # Slide the bounding box along the y-axis
        for y in range(0, saliency_frame.shape[0] - bb_height + 1, step_size):
            # Slide the bounding box along the x-axis
            for x in range(0, saliency_frame.shape[1] - bb_width + 1, step_size):
                # Calculate saliency captured by the current bounding box position
                saliency = self._saliency_captured(bb_height, bb_width, x, y, saliency_frame)
                # Update maximum saliency and corresponding position if needed
                if saliency > max_saliency:
                    max_saliency = saliency
                    max_x = x
                    max_y = y

        # Return the position with maximum saliency and other bounding box parameters
        return max_x, max_y, bb_width, bb_height

    def block_region(self, frame, bbox):
        """
        Block out a region in the frame specified by the bounding box.

        Args:
        - frame: The input frame.
        - bbox: Bounding box of the region to cut out

        Returns:
        - modified_frame: Frame with the specified region blocked out (salience set to 0).
        """
        bb_x, bb_y, bb_width, bb_height = bbox
        # Copy the original frame to avoid modifying it directly
        modified_frame = frame.copy()

        # Set the pixel values within the bounding box region to 0
        modified_frame[bb_y:bb_y + bb_height, bb_x:bb_x + bb_width] = 0

        return modified_frame

    def calculate_bounding_boxes_for_frame(self, frame, bb_height, bb_width):
        first_bbox = self.find_best_pos(bb_height, bb_width, frame)
        new_frame = self.block_region(frame, first_bbox)
        second_bbox = self.find_best_pos(bb_height, bb_width, new_frame)
        return [first_bbox, second_bbox]

    def generate_bounding_boxes(self, saliency_video_path):
        # Read the video saliency map
        saliency_video = cv2.VideoCapture(saliency_video_path)
        if not saliency_video.isOpened():
            print("Error: Unable to open saliency video file.")
            return []

        bb_height, bb_width = None, None

        # Initialize list to store bounding boxes
        bounding_boxes = []

        # Iterate over video frames to generate bounding boxes
        while True:
            # Read a frame from the saliency video
            success, frame = saliency_video.read()

            if not success:
                break

            if bb_width is None or bb_height is None:
                bb_height, bb_width = int(frame.shape[0] / 2), int((frame.shape[0] / 16) * 9)

                # Find x-position with maximum saliency for each frame
            frame_bboxes = self.calculate_bounding_boxes_for_frame(frame, bb_height, bb_width)

            # Append bounding box to the list
            bounding_boxes.append(frame_bboxes)

        # Release the video capture object
        saliency_video.release()
        return bounding_boxes

    def evaluate_saliency(self, saliency_video_path, bounding_boxes):
        cap = cv2.VideoCapture(saliency_video_path)
        evaluation_results = []
        frame_index = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            saliency_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            total_saliency = np.sum(saliency_frame)
            frame_saliency_sum = 0

            for bbox in bounding_boxes[frame_index]:
                x, y, w, h = bbox
                frame_saliency_sum += np.sum(saliency_frame[y:y + h, x:x + w])

            evaluation_results.append(frame_saliency_sum / total_saliency)

            frame_index += 1
        cap.release()
        return evaluation_results

    def stack_bounding_boxes(self, original_frame, bounding_boxes):
        """
        Stack two bounding boxes on top of each other.

        Args:
        - bounding_boxes: List containing tuples of bounding box coordinates (bb_x, bb_y, bb_width, bb_height) for each box.

        Returns:
        - stacked_frame: Frame with the two bounding boxes stacked vertically.
        """

        # Crop out each bounding box separately
        cropped_boxes = []
        for bb_x, bb_y, bb_width, bb_height in bounding_boxes:
            cropped_box = original_frame[bb_y:bb_y + bb_height, bb_x:bb_x + bb_width]
            cropped_boxes.append(cropped_box)

        # Calculate dimensions of the stacked frame
        stacked_height = sum(box.shape[0] for box in cropped_boxes)
        stacked_width = max(box.shape[1] for box in cropped_boxes)

        # Create the stacked frame
        stacked_frame = np.zeros((stacked_height, stacked_width, 3), dtype=np.uint8)

        # Position the cropped bounding boxes one beneath the other in the stacked frame
        y_offset = 0
        for cropped_box in cropped_boxes:
            h, w, _ = cropped_box.shape
            stacked_frame[y_offset:y_offset + h, :w] = cropped_box
            y_offset += h

        return stacked_frame

    def _crop_frame(self, original_frame, bboxes):
        """
        Crop a frame given the bounding box coordinates.

        Args:
        - original_frame: Original frame to be cropped.
        - bboxes: two bounding boxes

        Returns:
        - cropped_frame: Cropped frame based on the bounding box coordinates.
        """

        return self.stack_bounding_boxes(original_frame, bboxes)

    def crop_video(self, video_path, bounding_boxes, output_path, skip_frames=0):
        # Open the input video
        input_video = cv2.VideoCapture(video_path)
        if not input_video.isOpened():
            print("Error: Unable to open input video file.")
            return

        fps = int(input_video.get(cv2.CAP_PROP_FPS))
        # Calculate the number of frames actually processed during saliency video generation
        processed_frames = len(bounding_boxes)

        # Define the codec and create VideoWriter object
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        output_video = cv2.VideoWriter(output_path, fourcc, fps, (bounding_boxes[0][0][2], bounding_boxes[0][0][3] * 2))

        top_bounding_boxes = [i[0] for i in bounding_boxes]
        bottom_bounding_boxes = [i[1] for i in bounding_boxes]
        frame_indices = np.linspace(0, processed_frames - 1, processed_frames)
        top_interpolate_func = interp1d(frame_indices * (skip_frames + 1), top_bounding_boxes, axis=0, kind='linear')
        bottom_interpolate_func = interp1d(frame_indices * (skip_frames + 1), bottom_bounding_boxes, axis=0,
                                           kind='linear')

        # Process video frames
        frame_count = 0
        while True:
            # Read a frame from the input video
            success, frame = input_video.read()
            if not success:
                break

            # Interpolate the bounding boxes for the current frame
            top_interp_bb = top_interpolate_func(frame_count)
            bottom_interp_bb = bottom_interpolate_func(frame_count)

            # Crop the frame based on the interpolated bounding boxes
            cropped_frame = self._crop_frame(frame, (top_interp_bb.astype(int), bottom_interp_bb.astype(int)))

            # Write the cropped frame to the output video
            output_video.write(cropped_frame)

            # Increment frame count
            frame_count += 1

        # Release the video capture and writer objects
        input_video.release()
        output_video.release()

        # Add audio to the cropped video
        audio_clip = mp.AudioFileClip(video_path)
        cropped_video = mp.VideoFileClip(output_path)
        final_clip = cropped_video.set_audio(audio_clip)
        final_clip.write_videofile(output_path, codec='libx264')
