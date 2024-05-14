from .saliency_interface import VideoSaliencyDetector
import cv2
import numpy as np


class StaticSaliencyDetector(VideoSaliencyDetector):
    def load_and_prepare_frame(self, frame):
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        frame = np.float32(frame) / 255.0
        return frame

    def calculate_saliency(self, frame):
        saliency = cv2.saliency.StaticSaliencySpectralResidual_create()
        (success, saliency_map) = saliency.computeSaliency(frame)
        if not success:
            raise ValueError("Saliency computation failed.")
        saliency_map = (saliency_map * 255).astype("uint8")
        return saliency_map

    def save_saliency_map(self, saliency_map, output_writer):
        output_writer.write(saliency_map)

    def generate_video_saliency(self, video_path, skip_frames=5, save_path='saliency_video.avi'):
        cap = cv2.VideoCapture(video_path)
        frame_width = int(cap.get(3))
        frame_height = int(cap.get(4))
        out = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc('M','J','P','G'), 10, (frame_width, frame_height), isColor=False)

        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_count % skip_frames == 0:
                prepared_frame = self.load_and_prepare_frame(frame)
                saliency_map = self.calculate_saliency(prepared_frame)
                self.save_saliency_map(saliency_map, out)
            frame_count += 1

        cap.release()
        out.release()