from .saliency_interface import VideoSaliencyDetector
import numpy as np
import cv2
from tqdm import tqdm

class GridSaliencyDetector(VideoSaliencyDetector):
    def load_and_prepare_frame(self, frame):
        """Convert frame to grayscale and float32 for saliency calculation."""
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        frame = np.float32(frame) / 255.0
        return frame

    def calculate_saliency(self, frame):
        """Calculate the saliency map for a frame using the Static Saliency Spectral Residual method."""
        saliency = cv2.saliency.StaticSaliencySpectralResidual_create()
        success, saliency_map = saliency.computeSaliency(frame)
        if not success:
            raise ValueError("Saliency computation failed.")
        saliency_map = (saliency_map * 255).astype("uint8")
        return saliency_map

    def calculate_grid_saliency(self, saliency_map, grid_size=(10, 10)):
        """Calculate maximum or average saliency in each grid cell and remap to original size."""
        rows, cols = grid_size
        cell_height, cell_width = saliency_map.shape[0] // rows, saliency_map.shape[1] // cols
        grid_saliency = np.zeros_like(saliency_map)

        for i in range(rows):
            for j in range(cols):
                cell = saliency_map[i * cell_height:(i + 1) * cell_height, j * cell_width:(j + 1) * cell_width]
                # Using maximum saliency value for each grid cell here, replace with `np.mean(cell)` for average
                grid_saliency[i * cell_height:(i + 1) * cell_height, j * cell_width:(j + 1) * cell_width] = np.max(cell)

        return grid_saliency

    def save_saliency_map(self, saliency_map, output_writer):
        """Save the saliency map to an output."""
        if len(saliency_map.shape) == 2:  # Only height and width, no channels
            saliency_map = cv2.cvtColor(saliency_map, cv2.COLOR_GRAY2BGR)
        output_writer.write(saliency_map)

    def generate_video_saliency(self, video_path, skip_frames=5, save_path='saliency_video.avi', grid_size=(10, 10)):
        """Generate a saliency map for an entire video with grid-based saliency included."""
        cap = cv2.VideoCapture(video_path)
        frame_width = int(cap.get(3))
        frame_height = int(cap.get(4))
        # Ensure the codec is appropriate for the output format; here using 'XVID' for compatibility
        out = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc(*'XVID'), 10, (frame_width, frame_height), isColor=True)

        frame_count = 0
        pbar = tqdm(total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), desc="Processing Video")
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_count % skip_frames == 0:
                prepared_frame = self.load_and_prepare_frame(frame)
                saliency_map = self.calculate_saliency(prepared_frame)
                grid_saliency_map = self.calculate_grid_saliency(saliency_map, grid_size)
                self.save_saliency_map(grid_saliency_map, out)
            frame_count += 1
            pbar.update(1)

        pbar.close()
        cap.release()
        out.release()
