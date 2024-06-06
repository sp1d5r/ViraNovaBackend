import os

import numpy as np
import cv2
from skimage import segmentation
from tqdm import tqdm
from joblib import Parallel, delayed
from multiprocessing import Manager
from skimage.util import img_as_float
from services.saliency_detection.saliency_interface import VideoSaliencyDetector

import time
from datetime import datetime
from multiprocessing import Manager, Process

def update_progress(firebase_service, short_id, progress_value):
    firebase_service.update_document("shorts", short_id, {"update_progress": progress_value})

def update_message(firebase_service, short_id, message):
    firebase_service.update_document("shorts", short_id, {"progress_message": message, "last_updated": datetime.now()})

def monitor_progress(progress, short_id):
    from services.firebase import FirebaseService  # Import inside the function to avoid pickling issues
    firebase_service = FirebaseService()
    last_progress = 0
    while True:
        current_progress = progress.value
        if current_progress >= 100 or last_progress >= 100:
            break
        if current_progress != last_progress:
            update_progress(firebase_service, short_id, current_progress)
            last_progress = current_progress
        time.sleep(0.5)
    update_progress(firebase_service, short_id, 100)


class OpticFlowSegmentedSaliencyDetector(VideoSaliencyDetector):
    def adjust_gamma(self, frame, gamma=1.0):
        inv_gamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
        return cv2.LUT(frame, table)

    def apply_edge_detection(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=5)
        sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=5)
        sobel = cv2.magnitude(sobelx, sobely)
        return cv2.convertScaleAbs(sobel)

    def apply_gaussian_blur(self, frame, kernel_size=5):
        return cv2.GaussianBlur(frame, (kernel_size, kernel_size), 0)

    def apply_clahe(self, frame):
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2Lab)
        l, a, b = cv2.split(lab)
        if l.dtype != np.uint8:
            l = np.uint8(255 * (l / l.max()))
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        updated_lab = cv2.merge((l, a, b))
        return cv2.cvtColor(updated_lab, cv2.COLOR_Lab2BGR)

    def load_and_prepare_frame(self, frame):
        frame = self.apply_clahe(frame)
        frame = self.adjust_gamma(frame)
        frame = self.apply_gaussian_blur(frame)
        frame = img_as_float(frame).astype(np.float32)
        if frame.shape[-1] == 4:
            frame = frame[..., :3]
        return frame

    def calculate_optic_flow(self, prev_frame, next_frame):
        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        next_gray = cv2.cvtColor(next_frame, cv2.COLOR_BGR2GRAY)
        flow = cv2.calcOpticalFlowFarneback(prev_gray, next_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        return cv2.normalize(magnitude, None, 0, 1, cv2.NORM_MINMAX)

    def calculate_saliency(self, frame):
        saliency = cv2.saliency.StaticSaliencySpectralResidual_create()
        success, saliency_map = saliency.computeSaliency(frame)
        return (saliency_map * 255).astype(np.uint8) if success else np.zeros(frame.shape[:2], dtype=np.uint8)

    def segment_and_combine_saliency(self, frame, magnitude, type="max"):
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
        if saliency_map.dtype != np.uint8:
            saliency_map = cv2.normalize(saliency_map, None, 0, 255, cv2.NORM_MINMAX)
            saliency_map = saliency_map.astype(np.uint8)
        output_writer.write(saliency_map)

    def process_frame_chunk(self, frames, skip_frames, type, progress, total_frames, num_chunks):
        processed_results = []
        prev_frame = self.load_and_prepare_frame(frames[0])
        for frame_count, frame in enumerate(frames[1:], 1):
            next_frame = self.load_and_prepare_frame(frame)
            if frame_count % skip_frames == 0:
                magnitude = self.calculate_optic_flow(prev_frame, next_frame)
                saliency_map = self.segment_and_combine_saliency(next_frame, magnitude, type)
                processed_results.append(saliency_map)
                progress.value += (1 / total_frames) * 100
            prev_frame = next_frame
        return processed_results

    def generate_video_saliency(self, video_path, update_progress, short_id="", skip_frames=5, save_path='saliency_video.mp4', type="max"):
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_width, frame_height = int(cap.get(3)), int(cap.get(4))
        original_frame_rate = int(cap.get(cv2.CAP_PROP_FPS))
        effective_frame_rate = original_frame_rate / skip_frames

        frames = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frames.append(frame)
        cap.release()

        num_chunks = 4
        chunk_size = len(frames) // num_chunks

        frame_chunks = [frames[i:i + chunk_size] for i in range(0, len(frames), chunk_size)]
        manager = Manager()
        progress = manager.Value('d', 0.0)

        progress_monitor = Process(target=monitor_progress,
                                   args=(progress, short_id))
        progress_monitor.start()

        # Process frames in parallel
        processed_chunks = Parallel(n_jobs=num_chunks)(delayed(self.process_frame_chunk)(
            chunk, skip_frames, type, progress, total_frames//skip_frames, num_chunks) for chunk in frame_chunks)

        out = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc(*'mp4v'), effective_frame_rate, (frame_width, frame_height), isColor=False)

        # Flatten the list of processed frames
        processed_frames = [frame for chunk in processed_chunks for frame in chunk]

        # Write processed frames to the output video
        for frame in processed_frames:
            self.save_saliency_map(frame, out)
            update_progress(progress.value)  # Update the progress

        out.release()

        update_progress(100)