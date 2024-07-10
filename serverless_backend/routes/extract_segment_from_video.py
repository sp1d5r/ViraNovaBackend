import ast
import os
import tempfile
from flask import Blueprint, jsonify
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.video_clipper import VideoClipper

extract_segment_from_video = Blueprint("extract_segment_from_video", __name__)


def print_file_size(file_path):
    size = os.path.getsize(file_path)
    print(f"File size of {file_path} is {size} bytes.")


@extract_segment_from_video.route("/v1/crop-segment/<segment_id>", methods=['GET'])
def crop_video_to_segment(segment_id):
    try:
        firebase_service = FirebaseService()
        video_clipper = VideoClipper()

        print("Getting Documents")
        segment_document = firebase_service.get_document("topical_segments", segment_id)
        video_document = firebase_service.get_document('videos', segment_document['video_id'])
        update_progress = lambda x: firebase_service.update_document("topical_segments", segment_id, {'progress': x})
        update_progress_message = lambda x: firebase_service.update_document("topical_segments", segment_id, {'progress_message': x})
        firebase_service.update_document("topical_segments", segment_id, {'segment_status': "Getting Segment Video"})

        words = ast.literal_eval(segment_document['words'])
        begin_cut = words[0]['start_time']
        end_cut = words[-1]['end_time']
        video_path = video_document['videoPath']

        # 1) Load in video to memory
        update_progress_message("Getting video stream")
        update_progress(20)
        input_path = firebase_service.download_file_to_temp(video_document['videoPath'])
        print_file_size(input_path)

        # 2) Clip video to segment
        update_progress_message("Creating temporary video segment")
        update_progress(40)
        _, output_path = tempfile.mkstemp(suffix='.mp4')  # Ensure it's an mp4 file
        video_clipper.clip_video(input_path, begin_cut, end_cut, output_path)

        print_file_size(output_path)

        # 3) Reupload to firebase storage
        update_progress_message("Uploading to firebase")
        update_progress(60)
        destination_blob_name = "segments-video/" + segment_id + "-" + "".join(video_path.split("/")[1:])
        firebase_service.upload_file_from_temp(output_path, destination_blob_name)

        # 4) Update location on short document
        update_progress_message("Update location on short document")
        update_progress(80)
        firebase_service.update_document("topical_segments", segment_id, {"video_segment_location": destination_blob_name})

        # 5) Cleanup
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)

        return jsonify(
            {
                "status": "success",
                "data": {
                    "segment_id": segment_id,
                    "video_segment_location": destination_blob_name
                },
                "message": "Successfully cropped segment video"
            }), 200
    except Exception as e:
        return jsonify(
            {
                "status": "error",
                "data": {
                    "segment_id": segment_id,
                    "error": str(e)
                },
                "message": "Failed to cropped segment video"
            }), 400
