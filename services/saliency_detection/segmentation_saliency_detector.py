from .saliency_interface import VideoSaliencyDetector
import numpy as np
import cv2
from skimage import segmentation
from tqdm import tqdm
from skimage.util import img_as_float

class SegmentedSaliencyDetector(VideoSaliencyDetector):
    def load_and_prepare_frame(self, frame):
        """Convert frame to grayscale and float32 for saliency calculation."""
        frame = img_as_float(frame)  # Convert image to float for processing

        # Remove alpha channel if present
        if frame.shape[-1] == 4:
            frame = frame[..., :3]

        return frame

    def calculate_saliency(self, frame):
        """Calculate the saliency map for a frame using the Static Saliency Spectral Residual method."""
        # Convert image to float32 for compatibility with OpenCV Saliency API
        if frame.dtype != np.float32:
            frame = frame.astype(np.float32)
        saliency = cv2.saliency.StaticSaliencySpectralResidual_create()
        success, saliency_map = saliency.computeSaliency(frame)
        if not success:
            raise ValueError("Saliency computation failed.")
        saliency_map = (saliency_map * 255).astype("uint8")
        return saliency_map

    def segment_and_calculate_saliency(self, frame, type="max"):
        """Segment the frame and calculate average and max saliency per segment."""
        segments = segmentation.slic(frame, n_segments=200, compactness=10, sigma=1)
        saliency_map = self.calculate_saliency(frame)

        segment_saliency = np.zeros_like(saliency_map, dtype=np.float64)

        for segment_value in np.unique(segments):
            mask = segments == segment_value
            if type =="max":
                segment_saliency[mask] = np.max(saliency_map[mask])
            else:
                segment_saliency[mask] = np.mean(saliency_map[mask])

        # Map max saliency values back to the segment locations
        segment_saliency = (segment_saliency / segment_saliency.max() * 255).astype(np.uint8)
        return segment_saliency

    def save_saliency_map(self, saliency_map, output_writer):
        """Save the saliency map to an output."""
        output_writer.write(saliency_map)

    def generate_video_saliency(self, video_path, skip_frames=5, save_path='saliency_video.mp4', type="max"):
        """Generate a saliency map for an entire video with segmentation included."""
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))  # Get the total number of frames in the video
        frame_width = int(cap.get(3))
        frame_height = int(cap.get(4))

        # Calculate the frame rate based on the skip frames method
        original_frame_rate = cap.get(cv2.CAP_PROP_FPS)
        effective_frame_rate = original_frame_rate / skip_frames

        # Define the codec and create VideoWriter object
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Codec for MP4
        out = cv2.VideoWriter(save_path, fourcc, effective_frame_rate, (frame_width, frame_height), isColor=False)

        frame_count = 0
        pbar = tqdm(total=total_frames, desc="Processing Video")  # Initialize the progress bar
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_count % skip_frames == 0:
                prepared_frame = self.load_and_prepare_frame(frame)
                saliency_map = self.segment_and_calculate_saliency(prepared_frame, type=type)
                self.save_saliency_map(saliency_map, out)

            frame_count += 1
            pbar.update(1)  # Update the progress bar with each frame processed

        pbar.close()  # Close the progress bar after processing is complete
        cap.release()
        out.release()
