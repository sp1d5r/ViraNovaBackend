from beam import Image, endpoint, env, function
import os
import base64
import json
from datetime import datetime
import tempfile
import time


if env.is_remote():
    import firebase_admin
    from firebase_admin import credentials, firestore, storage
    import tensorflow as tf
    from huggingface_hub import snapshot_download
    import numpy as np
    import cv2
    from dotenv import load_dotenv

    load_dotenv()


def download_models():
    # Download the model files from Hugging Face
    hf_dir = snapshot_download(repo_id="alexanderkroner/MSI-Net")

    # Load the model using TensorFlow's saved_model format
    model = tf.saved_model.load(hf_dir)

    # If the model is not already in SavedModel format, you might need to use:
    # model = tf.keras.models.load_model(hf_dir)

    # Ensure the model is using GPU
    physical_devices = tf.config.list_physical_devices('GPU')
    if len(physical_devices) > 0:
        tf.config.experimental.set_memory_growth(physical_devices[0], True)

    return model

@function(secrets=["SERVICE_ACCOUNT_ENCODED", "FIREBASE_STORAGE_BUCKET"])
def get_secrets():
    return os.getenv('SERVICE_ACCOUNT_ENCODED'), os.getenv('FIREBASE_STORAGE_BUCKET')


class FirebaseService:
    def __init__(self):
        # Initialize the app with a service account, granting admin privileges
        encoded_json_str, storage_bucket = get_secrets()
        json_str = base64.b64decode(encoded_json_str).decode('utf-8')
        service_account_info = json.loads(json_str)
        self.cred = credentials.Certificate(service_account_info)
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


    def get_document(self, collection_name, document_id):
        # Retrieve an instance of a CollectionReference
        doc_ref = self.db.collection(collection_name).document(document_id)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        else:
            return None

    def update_document(self, collection_name, document_id, update_fields):
        """Updates specific fields of a document."""
        doc_ref = self.db.collection(collection_name).document(document_id)
        doc_ref.update(update_fields)
        return f"Document {document_id} in {collection_name} updated."



def perform_inference_on_video(model, video_path, update_progress, batch_size=3, skip_frames=2):
    # Open the video file
    cap = cv2.VideoCapture(video_path)

    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)

    frames = []
    frame_count = 0
    saliency_maps = []
    start_time = time.time()

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Skip frames if necessary
        if frame_count % (skip_frames + 1) != 0:
            frame_count += 1
            continue

        # Convert frame to RGB (OpenCV reads frames in BGR format)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frames.append(frame_rgb)

        # If we have enough frames for a batch, process them
        if len(frames) == batch_size:
            batch_saliency_maps = process_batch(model, frames)
            saliency_maps.extend(batch_saliency_maps)
            frames = []  # Reset the list for the next batch
        update_progress((frame_count / total_frames) * 100)
        frame_count += 1

    # Process any remaining frames
    if frames:
        batch_saliency_maps = process_batch(model, frames)
        saliency_maps.extend(batch_saliency_maps)

    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Time taken to process the video: {elapsed_time} seconds")

    cap.release()
    return saliency_maps

def process_batch(model, frames):
    batch_input_tensor, paddings = preprocess_batch(frames)
    output_tensors = model(batch_input_tensor)

    # Use the correct key from the model output
    if 'layer_from_saved_model' in output_tensors:
        output_tensors = output_tensors['layer_from_saved_model']
    else:
        raise KeyError(f"'layer_from_saved_model' key not found in model output. Available keys: {output_tensors.keys()}")

    batch_saliency_maps = []
    for I, output_tensor in enumerate(output_tensors):
        saliency_map = postprocess_output(
            output_tensor, paddings[I]['vertical'], paddings[I]['horizontal'], frames[I].shape[:2]
        )
        batch_saliency_maps.append(saliency_map)
    return batch_saliency_maps

def preprocess_batch(frames):
    batch_input_tensor = []
    paddings = []
    for frame in frames:
        original_shape = frame.shape[:2]
        target_shape = get_target_shape(original_shape)
        input_tensor, vertical_padding, horizontal_padding = preprocess_input(frame, target_shape)
        batch_input_tensor.append(input_tensor)
        paddings.append({'vertical': vertical_padding, 'horizontal': horizontal_padding})
    batch_input_tensor = np.vstack(batch_input_tensor)  # Combine into a single batch tensor
    return batch_input_tensor, paddings


# Placeholder functions for preprocessing and postprocessing
def get_target_shape(original_shape):
    original_aspect_ratio = original_shape[0] / original_shape[1]

    square_mode = abs(original_aspect_ratio - 1.0)
    landscape_mode = abs(original_aspect_ratio - 240 / 320)
    portrait_mode = abs(original_aspect_ratio - 320 / 240)

    best_mode = min(square_mode, landscape_mode, portrait_mode)

    if best_mode == square_mode:
        target_shape = (320, 320)
    elif best_mode == landscape_mode:
        target_shape = (240, 320)
    else:
        target_shape = (320, 240)

    return target_shape


def preprocess_input(input_image, target_shape):
    # Expand dimensions to add batch dimension
    input_tensor = tf.expand_dims(input_image, axis=0)

    # Resize the image while preserving aspect ratio
    input_tensor = tf.image.resize(input_tensor, target_shape, preserve_aspect_ratio=True)

    # Calculate padding needed to match target shape
    vertical_padding = target_shape[0] - input_tensor.shape[1]
    horizontal_padding = target_shape[1] - input_tensor.shape[2]

    vertical_padding_1 = vertical_padding // 2
    vertical_padding_2 = vertical_padding - vertical_padding_1

    horizontal_padding_1 = horizontal_padding // 2
    horizontal_padding_2 = horizontal_padding - horizontal_padding_1

    # Pad the resized image to match the target shape
    input_tensor = tf.pad(
        input_tensor,
        [
            [0, 0],
            [vertical_padding_1, vertical_padding_2],
            [horizontal_padding_1, horizontal_padding_2],
            [0, 0],
        ],
    )

    return (
        input_tensor,
        [vertical_padding_1, vertical_padding_2],
        [horizontal_padding_1, horizontal_padding_2],
    )

def postprocess_output(output_tensor, vertical_padding, horizontal_padding, original_shape):
    # Remove padding
    output_tensor = output_tensor[
        vertical_padding[0] : output_tensor.shape[0] - vertical_padding[1],
        horizontal_padding[0] : output_tensor.shape[1] - horizontal_padding[1],
        :
    ]

    # Resize to original shape
    output_tensor = tf.image.resize(output_tensor, original_shape)

    # Convert to numpy array and squeeze to remove batch dimension
    output_array = output_tensor.numpy().squeeze()

    return output_array


def create_video_from_frames(frames, original_video_path, skip_frames=2):
    # Open the original video to get properties
    cap = cv2.VideoCapture(original_video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps /= (skip_frames + 1)

    cap.release()

    print(f"FPS: {fps}, Width: {frame_width}, Height: {frame_height}")

    # Create a temporary file for the output video
    temp_video_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
    temp_video_path = temp_video_file.name

    out = cv2.VideoWriter(temp_video_path, cv2.VideoWriter_fourcc(*'avc1'), fps, (frame_width, frame_height), isColor=False)

    for frame in frames:
        # Ensure the frame is scaled correctly and converted to uint8
        frame = (frame * 255).astype(np.uint8)
        out.write(frame)

    out.release()
    print(f"Video saved to {temp_video_path}")
    return temp_video_path


@endpoint(
    name="saliency-endpoint",
    cpu=4,
    memory="30Gi",
    gpu="T4",
    on_start=download_models,
    image=Image(
        python_version="python3.9",
        python_packages=[
            "firebase-admin",
            "tensorflow",
            "keras",
            "huggingface_hub",
            "python-dotenv",
            "opencv-python-headless",
            "numpy"
        ],
    ),
    secrets=["FIREBASE_STORAGE_BUCKET", "SERVICE_ACCOUNT_ENCODED"],
)
def predict(context, short_id):
    if env.is_remote():
        print("Is built with CUDA:", tf.test.is_built_with_cuda())
        print("Is GPU available:", tf.test.is_gpu_available())

        # Retrieve cached model from on_start function
        model = context.on_start_value

        firebase_service = FirebaseService()

        short_document = firebase_service.get_document("shorts", short_id)
        if not short_document:
            return {"error_message": "Failed to get the short document"}

        update_progress = lambda x: firebase_service.update_document("shorts", short_id, {"update_progress": x})
        update_message = lambda x: firebase_service.update_document("shorts", short_id,
                                                                    {"progress_message": x,
                                                                     "last_updated": datetime.now()})

        update_message("Downloading the video to temporary location")
        update_progress(0)
        video_tmp_location = firebase_service.download_file_to_temp(short_document['short_clipped_video'])
        firebase_service.update_document('shorts', short_id, {
            "pending_operations": True
        })

        update_message("Calculating Saliency")
        saliency_map = perform_inference_on_video(model, video_tmp_location, update_progress, batch_size=2,
                                                  skip_frames=2)

        update_message("Collapsing saliency into video")
        output_video_path = create_video_from_frames(saliency_map, video_tmp_location)

        update_message("Updating document")
        short_video_path = short_document['short_clipped_video']
        destination_blob_name = "short-video-saliency/" + short_id + "-" + "".join(short_video_path.split("/")[1:])

        firebase_service.upload_file_from_temp(output_video_path, destination_blob_name)

        firebase_service.update_document('shorts', short_id, {
            "short_video_saliency": destination_blob_name,
            "pending_operations": False,
            "short_status": 'Determine Video Boundaries'
        })

        return {"blob_location": destination_blob_name}
    else:
        return {"error": "This function can only be run in a remote environment"}