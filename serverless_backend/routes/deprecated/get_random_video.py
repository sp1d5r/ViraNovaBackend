import os
import random
from flask import Blueprint, jsonify
get_random_video = Blueprint("get_random_video", __name__)

VIDEO_FOLDER = '/viranova_storage/'


@get_random_video.route("/get-random-video", methods=['GET'])
def get_random_video_hdf5():
    try:
        # List all files in the video directory
        files = os.listdir(VIDEO_FOLDER)
        # Filter out files to ensure we only get video files if needed
        video_files = [file for file in files if file.lower().endswith(('.hdf5', '.h5'))]
        if not video_files:
            return "No video files found", 404
        random_video = random.choice(video_files)
        return {"video_file": random_video}
    except Exception as e:
        return str(e), 500