import numpy as np
from services.segmentation_loader import load_video_data
from flask import Blueprint, jsonify

get_segmentation_mask = Blueprint("get_segmentation_mask", __name__)


VIDEO_FOLDER = '/viranova_storage/'

def convert(obj):
    if isinstance(obj, np.generic):
        return obj.item()
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, list):
        return [convert(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: convert(value) for key, value in obj.items()}
    else:
        return obj


@get_segmentation_mask.route("/load-segmentation-from-file/<video_file>/")
def return_segmentation_masks(video_file: str):
    try:
        video_handler = load_video_data(VIDEO_FOLDER + video_file)
        video_handler = convert(video_handler)
        return jsonify(video_handler)
    except Exception as e:
        return str(e), 500