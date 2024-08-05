import ast
from flask import Blueprint, jsonify
from serverless_backend.services.firebase import FirebaseService
from datetime import datetime
import tempfile
import os
from serverless_backend.services.handle_operations_from_logs import handle_operations_from_logs
from serverless_backend.services.video_clipper import VideoClipper


# Routes
create_short_video = Blueprint("create_short_video", __name__)

def merge_consecutive_cuts(cuts, max_duration):
    if not cuts:
        return []

    # Start with the first cut, but ensure it doesn't exceed the video duration
    merged_cuts = [(cuts[0][0], min(cuts[0][1], max_duration))]

    for current_start, current_end in cuts[1:]:
        last_start, last_end = merged_cuts[-1]

        # Cap the end time to the maximum duration of the video
        current_end = min(current_end, max_duration)

        # If the current start time is the same as the last end time, merge them
        if current_start == last_end:
            merged_cuts[-1] = (last_start, current_end)  # Extend the last segment
        else:
            merged_cuts.append((current_start, current_end))

    return merged_cuts

def print_file_size(file_path):
    size = os.path.getsize(file_path)
    print(f"File size of {file_path} is {size} bytes.")

@create_short_video.route("/v1/create-short-video/<short_id>", methods=['GET'])
def generate_short_video(short_id):
    try:
        firebase_service = FirebaseService()
        video_clipper = VideoClipper()

        short_document = firebase_service.get_document("shorts", short_id)
        segment_id = short_document['segment_id']
        segment_document = firebase_service.get_document("topical_segments", segment_id)
        update_progress = lambda x: firebase_service.update_document("shorts", short_id, {"update_progress": x})
        update_message = lambda x: firebase_service.update_document("shorts", short_id, {"progress_message": x, "last_updated": datetime.now()})

        firebase_service.update_document("shorts", short_id, {"pending_operation": True})
        update_message("Getting Documents")
        update_message("Getting logs")
        # Check if the segment has a video segment location
        logs = short_document['logs']
        update_progress(10)

        update_message("Loading segment video to temporary location")
        video_path = segment_document['video_segment_location']
        input_path = firebase_service.download_file_to_temp(video_path)
        video_duration = video_clipper.get_video_duration(input_path)
        print_file_size(input_path)
        update_progress(10)

        update_message("Loading Operations")
        segment_document_words = ast.literal_eval(segment_document['words'])
        start_time = segment_document_words[0]['start_time']
        update_message("Read Segment Words")
        words_to_handle = handle_operations_from_logs(logs, segment_document_words)
        words_to_handle = [
            {**word, 'end_time': min(word['end_time'], words_to_handle[i + 1]['start_time'])}
            if i + 1 < len(words_to_handle) else word
            for i, word in enumerate(words_to_handle)
        ]
        update_message("Get clips start and end")
        update_progress(10)

        keep_cuts = [(round(i['start_time'] - start_time, 3), round(i['end_time'] - start_time,3)) for i in words_to_handle]
        merge_cuts = merge_consecutive_cuts(keep_cuts, video_duration)
        update_progress(20)

        # 3) Clip the short according to locations
        update_message("Creating temporary video segment")
        _, output_path = tempfile.mkstemp(suffix='.mp4')  # Ensure it's an mp4 file
        update_progress_time = lambda x: update_progress(30 + 50 * (x / 100))
        video_clipper.delete_segments_from_video(input_path, merge_cuts, output_path, update_progress_time)
        print_file_size(output_path)

        update_message("Uploading clipped video to short location")
        destination_blob_name = "short-video/" + short_id + "-" + "".join(video_path.split("/")[1:])
        firebase_service.upload_file_from_temp(output_path, destination_blob_name)
        update_progress(85)

        update_message("Updating short document")
        firebase_service.update_document("shorts", short_id, {"short_clipped_video": destination_blob_name})
        update_progress(90)

        update_message("Clean up...")
        update_progress(100)
        firebase_service.update_document("shorts", short_id, {"pending_operation": False, 'short_status': 'Generate Saliency'})
        if os.path.exists(input_path):
            os.remove(input_path)
        return jsonify(
            {
                "status": "success",
                "data": {
                    "short_id": short_id,
                    "short_clipped_video": destination_blob_name
                },
                "message": "Successfully created clipped video"
            }), 200
    except Exception as e:
        return jsonify(
            {
                "status": "error",
                "data": {
                    "short_id": short_id,
                    "error": str(e)
                },
                "message": "Failed to create clipped video"
            }), 400
