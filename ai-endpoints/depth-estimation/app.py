from beam import App, Runtime, Image
import torch
import cv2
import tempfile
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from firebase_admin import storage
import base64
import numpy as np
import os
import json
from dotenv import load_dotenv


load_dotenv()


class FirebaseService:
    def __init__(self):
        # Initialize the app with a service account, granting admin privileges
        encoded_json_str = os.getenv('SERVICE_ACCOUNT_ENCODED')
        json_str = base64.b64decode(encoded_json_str).decode('utf-8')
        service_account_info = json.loads(json_str)
        self.cred = credentials.Certificate(service_account_info)
        storage_bucket = os.getenv('FIREBASE_STORAGE_BUCKET')
        if not firebase_admin._apps:
            self.app = firebase_admin.initialize_app(self.cred, {
                'storageBucket': storage_bucket
            })
        self.db = firestore.client()
        self.bucket = storage.bucket()

    def download_file_to_temp(self, blob_name, suffix=".mp4"):
        """Downloads a file from Firebase Storage to a temporary file and returns the file path."""
        blob = self.bucket.blob(blob_name)
        _, temp_local_path = tempfile.mkstemp(suffix=suffix)
        blob.download_to_filename(temp_local_path)
        return temp_local_path

    def upload_file_from_temp(self, file_path, destination_blob_name):
        """Uploads a file from a temporary file to Firebase Storage."""
        blob = self.bucket.blob(destination_blob_name)
        blob.upload_from_filename(file_path)
        os.remove(file_path)


app = App(
    name="inference-quickstart",
    runtime=Runtime(
        cpu=1,
        memory="8Gi",
        gpu="T4",
        image=Image(
            python_version="python3.9",
            python_packages=[
                "opencv-python",
                "torch",
                "firebase-admin",
                "numpy",
                "python-dotenv",
                "timm"
            ],
        ),
    ),
)


def load_models():
    model_type = "DPT_Large"
    model = torch.hub.load("intel-isl/MiDaS", model_type)
    midas_transforms = torch.hub.load("intel-isl/MiDaS", "transforms")

    if model_type == "DPT_Large" or model_type == "DPT_Hybrid":
        transform = midas_transforms.dpt_transform
    else:
        transform = midas_transforms.small_transform

    return model, transform


def cache_video_frames(video_path):
    cap = cv2.VideoCapture(video_path)
    frames = []

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)

    cap.release()
    return frames


def frames_to_video(original_video_path, output_frames):
    # Read the original video to get frame rate and size
    original_video = cv2.VideoCapture(original_video_path)
    if not original_video.isOpened():
        print("Error opening video file")
        return

    # Get frame rate of the original video
    fps = original_video.get(cv2.CAP_PROP_FPS)
    width = int(original_video.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(original_video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    original_video.release()

    _, output_video_path = tempfile.mkstemp(suffix="mp4")

    # Define the codec and create VideoWriter object
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # or 'XVID', 'MJPG', 'X264', etc.
    out = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height), isColor=False)

    for frame in output_frames:
        if frame is None:
            print("Error reading frame")
            continue

        # Ensure the frame is a numpy array
        frame = np.array(frame.to('cpu'))

        # Normalize the frame values to be in the range 0-255
        frame_normalized = cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

        # Write the normalized grayscale frame to the video
        out.write(frame_normalized)

    out.release()
    print(f"Video saved as {output_video_path}")
    return output_video_path


@app.rest_api(loader=load_models)
def predict(**inputs):
    if "blob_location" not in inputs:
        return {"Error": "Blob location not found in inputs"}

    if "short_id" not in inputs:
        return {"Error": "Short ID not found in inputs"}

    # Retrieve cached model from loader
    model, transform = inputs["context"]
    firebase_service = FirebaseService()
    device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
    model.to(device)
    print("Currently using device:", device)

    temp_location = firebase_service.download_file_to_temp(inputs['blob_location'])
    frames = cache_video_frames(temp_location)

    input_batch = [transform(frame).to(device) for frame in frames]
    output_frames = []
    with torch.no_grad():
        for input_frame in input_batch:
            prediction = model(input_frame)

            prediction = torch.nn.functional.interpolate(
                prediction.unsqueeze(1),
                size=frames[0].shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()

            output_frames.append(prediction)


    output_path = frames_to_video(temp_location, output_frames)
    output_blob_location = "/depth-estimation/" + inputs["short_id"] + "/" + output_path.split("/")[-1]
    firebase_service.upload_file_from_temp(output_path, output_blob_location)

    return {"blob_location": output_blob_location}
