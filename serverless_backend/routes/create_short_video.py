import ast

from firebase_admin import firestore
from flask import Blueprint, jsonify

from serverless_backend.routes.extract_segment_from_video import crop_video_to_segment
from serverless_backend.services.firebase import FirebaseService
from datetime import datetime
import tempfile
import os
from serverless_backend.services.handle_operations_from_logs import handle_operations_from_logs
from serverless_backend.services.parse_segment_words import parse_segment_words
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

@create_short_video.route("/v1/create-short-video/<request_id>", methods=['GET'])
def generate_short_video(request_id):
    firebase_service = FirebaseService()
    video_clipper = VideoClipper()

    try:
        request_doc = firebase_service.get_document("requests", request_id)
        if not request_doc:
            return jsonify({"status": "error", "message": "Request not found"}), 404

        short_id = request_doc.get('shortId')
        if not short_id:
            return jsonify({"status": "error", "message": "Short ID not found in request"}), 400

        short_document = firebase_service.get_document("shorts", short_id)
        if not short_document:
            return jsonify({"status": "error", "message": "Short document not found"}), 404

        segment_id = short_document['segment_id']
        segment_document = firebase_service.get_document("topical_segments", segment_id)

        def update_progress(progress):
            firebase_service.update_document("shorts", short_id, {"update_progress": progress})
            firebase_service.update_document("requests", request_id, {"progress": progress})

        def update_message(message):
            firebase_service.update_document("shorts", short_id, {
                "progress_message": message,
                "last_updated": firestore.firestore.SERVER_TIMESTAMP
            })
            firebase_service.update_message(request_id, message)

        firebase_service.update_document("shorts", short_id, {"pending_operation": True})
        update_message("Getting Documents")
        update_message("Getting logs")
        logs = short_document['logs']
        update_progress(10)

        update_message("Loading segment video to temporary location")

        video_path = "None"
        if 'video_segment_location' in segment_document.keys():
            video_path = segment_document['video_segment_location']
        else:
            firebase_service.update_document("shorts", short_id, {"pending_operation": False})
            response, status_code = crop_video_to_segment(segment_id)
            segment_document = firebase_service.get_document("topical_segments", segment_id)
            if 'video_segment_location' in segment_document.keys():
                video_path = segment_document['video_segment_location']
            else:
                update_message("Failed to get video segment location")
                return response, status_code

        firebase_service.update_document("shorts", short_id, {"pending_operation": True})
        input_path = firebase_service.download_file_to_temp(video_path)
        video_duration = video_clipper.get_video_duration(input_path)
        print_file_size(input_path)
        update_progress(20)

        update_message("Loading Operations")

        try:
            segment_document_words = parse_segment_words(segment_document)
        except ValueError as e:
            error_message = f"Error parsing segment words: {str(e)}"
            update_message(error_message)
            firebase_service.update_document("shorts", short_id, {"pending_operation": False})
            return jsonify({
                "status": "error",
                "data": {"request_id": request_id, "short_id": short_id, "error": error_message},
                "message": "Failed to parse segment words"
            }), 400

        start_time = segment_document_words[0]['start_time']
        update_message("Read Segment Words")
        words_to_handle = handle_operations_from_logs(logs, segment_document_words)
        words_to_handle = [
            {**word, 'end_time': min(word['end_time'], words_to_handle[i + 1]['start_time'])}
            if i + 1 < len(words_to_handle) else word
            for i, word in enumerate(words_to_handle)
        ]
        update_message("Get clips start and end")
        update_progress(30)

        keep_cuts = [(round(i['start_time'] - start_time, 3), round(i['end_time'] - start_time,3)) for i in words_to_handle]
        merge_cuts = merge_consecutive_cuts(keep_cuts, video_duration)
        update_progress(40)

        update_message("Creating temporary video segment")
        _, output_path = tempfile.mkstemp(suffix='.mp4')
        update_progress_time = lambda x: update_progress(50 + 30 * (x / 100))
        video_clipper.delete_segments_from_video(input_path, merge_cuts, output_path, update_progress_time)
        print_file_size(output_path)

        update_message("Uploading clipped video to short location")
        destination_blob_name = "short-video/" + short_id + "-" + "".join(video_path.split("/")[1:])
        firebase_service.upload_file_from_temp(output_path, destination_blob_name)
        update_progress(90)

        update_message("Updating short document")
        firebase_service.update_document("shorts", short_id, {"short_clipped_video": destination_blob_name})
        update_progress(95)

        update_message("Clean up...")
        update_progress(100)

        if os.path.exists(input_path):
            os.remove(input_path)

        update_message("Short video creation completed successfully")
        firebase_service.create_short_request(
            "v1/get_saliency_for_short",
            short_id,
            request_doc.get('uid', "SERVER REQUEST")
        )

        return jsonify({
            "status": "success",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
                "short_clipped_video": destination_blob_name
            },
            "message": "Successfully created clipped video"
        }), 200

    except Exception as e:
        error_message = f"Failed to create clipped video: {str(e)}"
        update_message(error_message)
        firebase_service.update_document("shorts", short_id, {"pending_operation": False})
        return jsonify({
            "status": "error",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
                "error": str(e)
            },
            "message": error_message
        }), 500
