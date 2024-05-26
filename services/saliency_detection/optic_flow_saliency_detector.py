import numpy as np
import cv2
from tqdm import tqdm
from skimage.util import img_as_float
from services.saliency_detection.saliency_interface import VideoSaliencyDetector


class OpticFlowSaliencyDetector(VideoSaliencyDetector):
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
        # Convert frames to grayscale
        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        next_gray = cv2.cvtColor(next_frame, cv2.COLOR_BGR2GRAY)

        # Compute the optical flow
        flow = cv2.calcOpticalFlowFarneback(prev_gray, next_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        # Compute the magnitude and angle of the 2D vectors
        magnitude, angle = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        # Normalize magnitude from 0 to 1
        magnitude = cv2.normalize(magnitude, None, 0, 1, cv2.NORM_MINMAX)
        return magnitude

    def calculate_saliency(self, frame):
        """Calculate the saliency map for a frame using the Static Saliency Spectral Residual method."""
        if frame.dtype != np.float32:
            frame = frame.astype(np.float32)
        saliency = cv2.saliency.StaticSaliencySpectralResidual_create()
        success, saliency_map = saliency.computeSaliency(frame)
        if not success:
            # If computation fails, return a zero array instead of None
            return np.zeros(frame.shape[:2], dtype=np.float32)
        saliency_map = (saliency_map * 255).astype(np.uint8)
        return saliency_map

    def calculate_combined_saliency(self, frame, magnitude):
        static_saliency = self.calculate_saliency(frame)
        # Combine static saliency with the magnitude of optical flow
        combined_saliency = cv2.addWeighted(static_saliency.astype(np.float32), 0.05, magnitude, 0.95, 0)
        return combined_saliency

    def save_saliency_map(self, saliency_map, output_writer):
        """Save the saliency map to an output."""
        if saliency_map.dtype != np.uint8:
            # Normalize the saliency map to range 0 to 255, and convert to uint8
            saliency_map = cv2.normalize(saliency_map, None, 0, 255, cv2.NORM_MINMAX)
            saliency_map = saliency_map.astype(np.uint8)
        output_writer.write(saliency_map)

    def generate_video_saliency(self, video_path, skip_frames=5, save_path='saliency_video.mp4', type="max"):
        cap = cv2.VideoCapture(video_path)
        ret, prev_frame = cap.read()
        prev_frame = self.load_and_prepare_frame(prev_frame)

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))  # Get the total number of frames in the video
        frame_width = int(cap.get(3))
        frame_height = int(cap.get(4))

        # Calculate the frame rate based on the skip frames method
        original_frame_rate = int(cap.get(cv2.CAP_PROP_FPS))
        effective_frame_rate = original_frame_rate / skip_frames

        # Define the codec and create VideoWriter object
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Codec for MP4
        out = cv2.VideoWriter(save_path, fourcc, effective_frame_rate, (frame_width, frame_height), isColor=False)

        frame_count = 0
        pbar = tqdm(total=total_frames, desc="Processing Video")  # Initialize the progress bar

        while True:
            ret, next_frame = cap.read()
            if not ret:
                break
            next_frame = self.load_and_prepare_frame(next_frame)
            if frame_count % skip_frames == 0:
                magnitude = self.calculate_optic_flow(prev_frame, next_frame)
                saliency_map = self.calculate_combined_saliency(next_frame, magnitude)
                self.save_saliency_map(saliency_map, out)

            prev_frame = next_frame
            frame_count += 1
            pbar.update(1)
