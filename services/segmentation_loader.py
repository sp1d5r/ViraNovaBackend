import h5py
import numpy as np
from PIL import Image
import base64
from io import BytesIO

def array_to_base64(array):
    # Convert NumPy array to PIL Image
    image = Image.fromarray(array.astype('uint8'), 'RGB')
    # Create a buffer to hold the bytes
    buffer = BytesIO()
    # Save the image as PNG to the buffer
    image.save(buffer, format="PNG")
    # Encode the bytes as base64
    base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
    # Return the base64-encoded image
    return base64_image


# Convert all np.int64 elements to Python integers
def convert_numpy_ints(obj):
    if isinstance(obj, list):
        return [convert_numpy_ints(item) for item in obj]
    elif isinstance(obj, np.int64):
        return int(obj)  # or obj.item() to convert to native Python type
    else:
        return obj


def load_video_data(hdf5_file_path):
    video_data = {}

    with h5py.File(hdf5_file_path, 'r') as hdf5_file:
        # Retrieve the attributes for the whole video
        video_id = hdf5_file.attrs['video_id']
        duration = hdf5_file.attrs['duration']
        fps = hdf5_file.attrs['fps']

        # Initialize containers for frames and masks
        frames = []
        masks = []

        # Load frames
        frames_group = hdf5_file['frames']
        for frame_name in frames_group:
            frame = array_to_base64(frames_group[frame_name][...])
            frames.append(frame)  # '...' is used to read the full dataset

        # Load masks
        masks_group = hdf5_file['masks']
        for mask_name in masks_group:
            mask_array = masks_group[mask_name][...]  # Load the mask as a NumPy array
            mask_list = mask_array.tolist()  # Convert the NumPy array to a Python list
            mask_list_converted = convert_numpy_ints(mask_list)
            masks.append(mask_list_converted)

        video_data['video_id'] = video_id
        video_data['duration'] = duration
        video_data['fps'] = fps
        video_data['frames'] = frames
        video_data['masks'] = masks

    return video_data
