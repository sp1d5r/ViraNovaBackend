from abc import ABC, abstractmethod


class BoundingBoxGenerator(ABC):
    @abstractmethod
    def generate_bounding_boxes(self, saliency_video_path, start_frame, end_frame):
        """Generate bounding boxes from a video saliency map located at a specified path."""
        pass

    @abstractmethod
    def evaluate_saliency(self, saliency_video_path, bounding_boxes, start_frame, end_frame):
        """Evaluate the effectiveness of saliency within the bounding boxes across video frames."""
        pass

    @abstractmethod
    def crop_video(self, video_path, bounding_boxes, output_path):
        """Crop the video based on the generated bounding boxes and save it to the specified path."""
        pass