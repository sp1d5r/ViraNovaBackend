import ast
import os
import tempfile

from flask import Blueprint
from services.firebase import FirebaseService
from services.video_clipper import VideoClipper

extract_segment_from_video = Blueprint("extract_segment_from_video", __name__)


def print_file_size(file_path):
    size = os.path.getsize(file_path)
    print(f"File size of {file_path} is {size} bytes.")


@extract_segment_from_video.route("/crop-segment/<segment_id>")
def crop_video_to_segment(segment_id):
    firebase_service = FirebaseService()
    video_clipper = VideoClipper()

    print("Getting Documents")
    segment_document = firebase_service.get_document("topical_segments", segment_id)
    video_document = firebase_service.get_document('videos', segment_document['video_id'])

    firebase_service.update_document("topical_segments", segment_id, {'segment_status': "Getting Segment Video"})

    words = ast.literal_eval(segment_document['words'])
    begin_cut = words[0]['start_time']
    end_cut = words[-1]['end_time']
    video_path = video_document['videoPath']

    # 1) Load in video to memory
    print("Getting video stream")
    input_path = firebase_service.download_file_to_temp(video_document['videoPath'])
    print_file_size(input_path)

    # 2) Clip video to segment
    print("Creating temporary video segment")
    _, output_path = tempfile.mkstemp(suffix='.mp4')  # Ensure it's an mp4 file
    video_clipper.clip_video(input_path, begin_cut, end_cut, output_path)

    print_file_size(output_path)

    # 3) Reupload to firebase storage
    print("Uploading to firebase")
    destination_blob_name = "segments-video/" + segment_id + "-" + "".join(video_path.split("/")[1:])
    firebase_service.upload_file_from_temp(output_path, destination_blob_name)

    # 4) Update location on short document
    firebase_service.update_document("topical_segments", segment_id, {"video_segment_location": destination_blob_name})

    # 5) Cleanup
    os.remove(input_path)
    os.remove(output_path)