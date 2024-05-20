import numpy as np
import cv2

class VideoAnalyser():
    def get_differences(self, video_path):
        # Load the video
        cap = cv2.VideoCapture(video_path)

        # Check if the video has been opened successfully
        if not cap.isOpened():
            print("Error: Could not open video.")
            exit()
            return None, None

        prev_frame = None
        differences = []  # List to store the difference values
        last_frames = 0  # Optional: store frames for manual review

        while True:
            ret, frame = cap.read()
            if not ret:
                break  # If no frame is read, end of video

            # Convert frame to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            last_frames += 1

            if prev_frame is not None:
                # Compute the difference between current frame and the previous frame
                diff = cv2.absdiff(prev_frame, gray)
                _, thresh = cv2.threshold(diff, 50, 255, cv2.THRESH_BINARY)
                change_intensity = np.sum(thresh)
                differences.append(float(change_intensity))

            # Update the previous frame
            prev_frame = gray

        cap.release()

        return differences, last_frames

    def get_camera_cuts(self, differences):
        mean_difference = np.mean(differences)
        std = np.std(differences)
        threshold = mean_difference + 5 * std
        cuts = [i for i, diff in enumerate(differences) if diff > threshold]
        return cuts