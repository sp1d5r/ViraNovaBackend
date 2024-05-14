from abc import ABC, abstractmethod


class VideoSaliencyDetector(ABC):
    @abstractmethod
    def generate_video_saliency(self, video_path, skip_frames, save_path):
        """Generate a saliency map for an entire video read from a given path, with options to skip frames and save output."""
        pass

    @abstractmethod
    def load_and_prepare_frame(self, frame):
        """Prepare a frame for saliency computation."""
        pass

    @abstractmethod
    def calculate_saliency(self, frame):
        """Calculate the saliency map for a frame."""
        pass

    @abstractmethod
    def save_saliency_map(self, saliency_map, output_writer):
        """Save or handle the saliency map output."""
        pass