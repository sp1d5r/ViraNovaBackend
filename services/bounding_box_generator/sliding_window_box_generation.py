import cv2
import numpy as np
from .bounding_box_interface import BoundingBoxGenerator
from scipy.interpolate import interp1d
import moviepy.editor as mp

class SlidingWindowBoundingBoxGenerator(BoundingBoxGenerator):
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

    def _find_x_pos_max(self, bb_height, bb_width, saliency_frame):
        """
        Find the x-position that maximizes the saliency captured by a bounding box of given dimensions.

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

        # Slide the bounding box along the x-axis
        for x in range(0, saliency_frame.shape[1] - bb_width + 1, self.step_size):
            # Calculate saliency captured by the current bounding box position
            saliency = self._saliency_captured(bb_height, bb_width, x, 0, saliency_frame)
            # Update maximum saliency and corresponding x-position if needed
            if saliency > max_saliency:
                max_saliency = saliency
                max_x = x

        # Return the x-position with maximum saliency and other bounding box parameters
        return max_x, 0, bb_width, bb_height

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
                bb_height, bb_width = frame.shape[0], int((frame.shape[0] / 16) * 9)

                # Find x-position with maximum saliency for each frame
            bb_x, bb_y, bb_width, bb_height = self._find_x_pos_max(bb_height, bb_width, frame)

            # Append bounding box to the list
            bounding_boxes.append((bb_x, bb_y, bb_width, bb_height))

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
            x, y, w, h = bounding_boxes[frame_index]
            total_saliency = np.sum(saliency_frame)
            frame_saliency_sum = np.sum(saliency_frame[y:y + h, x:x + w])
            evaluation_results.append(frame_saliency_sum / total_saliency)

            frame_index += 1
        cap.release()
        return evaluation_results

    def _crop_frame(self, original_frame, bb_x, bb_y, bb_height, bb_width):
        """
        Crop a frame given the bounding box coordinates.

        Args:
        - original_frame: Original frame to be cropped.
        - bb_x: x-coordinate of the bounding box.
        - bb_y: y-coordinate of the bounding box.
        - bb_height: Height of the bounding box.
        - bb_width: Width of the bounding box.

        Returns:
        - cropped_frame: Cropped frame based on the bounding box coordinates.
        """

        # Crop the frame based on the bounding box coordinates
        cropped_frame = original_frame[bb_y:bb_y + bb_height, bb_x:bb_x + bb_width]

        return cropped_frame

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
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        output_video = cv2.VideoWriter(output_path, fourcc, fps, (bounding_boxes[0][2], bounding_boxes[0][3]))

        # Interpolate bounding boxes for the number of frames actually processed
        frame_indices = np.linspace(0, processed_frames - 1, processed_frames)
        interpolate_func = interp1d(frame_indices * (skip_frames + 1), bounding_boxes, axis=0, kind='linear')

        # Process video frames
        frame_count = 0
        while True:
            # Read a frame from the input video
            success, frame = input_video.read()
            if not success:
                break

            # Interpolate the bounding box for the current frame
            interp_bb = interpolate_func(frame_count)
            bb_x, bb_y, bb_width, bb_height = interp_bb.astype(int)

            # Crop the frame based on the bounding box
            cropped_frame = self._crop_frame(frame, bb_x, bb_y, bb_height, bb_width)

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