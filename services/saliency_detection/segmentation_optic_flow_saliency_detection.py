import numpy as np
import cv2
from skimage import segmentation
from tqdm import tqdm
from skimage.util import img_as_float
from services.saliency_detection.saliency_interface import VideoSaliencyDetector

class OpticFlowSegmentedSaliencyDetector(VideoSaliencyDetector):
    def adjust_gamma(self, frame, gamma=1.0):
        # Build a lookup table mapping the pixel values [0, 255] to
        # their adjusted gamma values
        inv_gamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** inv_gamma) * 255
                          for i in np.arange(0, 256)]).astype("uint8")

        # Apply gamma correction using the lookup table
        return cv2.LUT(frame, table)

    def apply_edge_detection(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=5)
        sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=5)
        sobel = cv2.magnitude(sobelx, sobely)
        return cv2.convertScaleAbs(sobel)

    def apply_gaussian_blur(self, frame, kernel_size=5):
        blurred_frame = cv2.GaussianBlur(frame, (kernel_size, kernel_size), 0)
        return blurred_frame

    def apply_clahe(self, frame):
        # Convert the frame to the Lab color space
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2Lab)
        l, a, b = cv2.split(lab)

        # Explicitly convert L channel to 8-bit if necessary
        if l.dtype != np.uint8:
            l = np.uint8(255 * (l / l.max()))  # Normalize and convert to uint8

        # Create a CLAHE object (with optional clip limit and grid size)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)  # Apply CLAHE to the L channel

        # Merge the Lab channels back together and convert back to BGR
        updated_lab = cv2.merge((l, a, b))
        enhanced_frame = cv2.cvtColor(updated_lab, cv2.COLOR_Lab2BGR)
        return enhanced_frame


    def load_and_prepare_frame(self, frame):
        """Convert frame to float32 for processing and ensure it's in the correct format for OpenCV."""
        # Apply pre-processing techniques
        frame = self.apply_clahe(frame)
        frame = self.adjust_gamma(frame)
        frame = self.apply_gaussian_blur(frame)
        frame = img_as_float(frame).astype(np.float32)
        if frame.shape[-1] == 4:
            frame = frame[..., :3]
        return frame


    def calculate_optic_flow(self, prev_frame, next_frame):
        """Calculate optic flow between two frames."""
        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        next_gray = cv2.cvtColor(next_frame, cv2.COLOR_BGR2GRAY)
        flow = cv2.calcOpticalFlowFarneback(prev_gray, next_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        magnitude = cv2.normalize(magnitude, None, 0, 1, cv2.NORM_MINMAX)
        return magnitude

    def calculate_saliency(self, frame):
        """Calculate static saliency map using spectral residual method."""
        saliency = cv2.saliency.StaticSaliencySpectralResidual_create()
        success, saliency_map = saliency.computeSaliency(frame)
        return (saliency_map * 255).astype(np.uint8) if success else np.zeros(frame.shape[:2], dtype=np.uint8)

    def segment_and_combine_saliency(self, frame, magnitude, type="max"):
        """Segment frame and calculate combined saliency for each segment."""
        segments = segmentation.slic(frame, n_segments=200, compactness=10, sigma=1)
        static_saliency = self.calculate_saliency(frame)
        combined_saliency = cv2.addWeighted(static_saliency.astype(np.float32), 0.1, magnitude, 0.9, 0)

        segment_saliency = np.zeros_like(combined_saliency, dtype=np.float32)
        for segment_value in np.unique(segments):
            mask = segments == segment_value
            if type == "max":
                segment_saliency[mask] = np.max(combined_saliency[mask])
            else:
                segment_saliency[mask] = np.mean(combined_saliency[mask])

        return (segment_saliency / segment_saliency.max() * 255).astype(np.uint8)

    def save_saliency_map(self, saliency_map, output_writer):
        """Save the saliency map to an output."""
        if saliency_map.dtype != np.uint8:
            # Normalize the saliency map to range 0 to 255, and convert to uint8
            saliency_map = cv2.normalize(saliency_map, None, 0, 255, cv2.NORM_MINMAX)
            saliency_map = saliency_map.astype(np.uint8)
        output_writer.write(saliency_map)

    def generate_video_saliency(self, video_path, update_progress, skip_frames=5, save_path='saliency_video.mp4',
                                type="max"):
        cap = cv2.VideoCapture(video_path)
        ret, prev_frame = cap.read()
        prev_frame = self.load_and_prepare_frame(prev_frame)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_width, frame_height = int(cap.get(3)), int(cap.get(4))
        original_frame_rate = int(cap.get(cv2.CAP_PROP_FPS))
        effective_frame_rate = original_frame_rate / skip_frames
        out = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc(*'mp4v'), effective_frame_rate,
                              (frame_width, frame_height), isColor=False)

        # Initial progress update (assuming some pre-processing)
        update_progress(5)

        frame_count = 0
        # Adjust total progress based on processing steps (excluding pre-processing)
        total_processing_steps = total_frames // skip_frames
        pbar = tqdm(total=total_processing_steps, desc="Processing Video")

        while True:
            ret, next_frame = cap.read()
            if not ret:
                break
            next_frame = self.load_and_prepare_frame(next_frame)

            if frame_count % skip_frames == 0:
                # Calculate progress based on processed frames (excluding skipped frames)
                processed_frames = frame_count // skip_frames
                progress = 5 + (processed_frames / total_processing_steps) * 90  # Adjust weights as needed
                update_progress(progress)

                magnitude = self.calculate_optic_flow(prev_frame, next_frame)
                saliency_map = self.segment_and_combine_saliency(next_frame, magnitude, type)
                self.save_saliency_map(saliency_map, out)
            prev_frame = next_frame
            frame_count += 1
            pbar.update(1)  # tqdm internal counter (not affecting update_progress)

        pbar.close()
        cap.release()
        out.release()
