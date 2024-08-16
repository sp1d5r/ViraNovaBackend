import ast
import os
import tempfile
import json
from datetime import datetime

from firebase_admin import firestore
from flask import Blueprint, jsonify

from serverless_backend.routes.generate_test_audio import generate_test_audio_for_short
from serverless_backend.routes.spacial_segmentation import add_audio_to_video
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.verify_video_document import parse_and_verify_short
from serverless_backend.services.bounding_box_generator.video_cropper import VideoCropper

generate_a_roll = Blueprint("generate_a_roll", __name__)

@generate_a_roll.route("/v1/generate-a-roll/<request_id>", methods=['GET'])
def generate_a_roll_short(request_id):
    firebase_services = FirebaseService()
    request_doc = firebase_services.get_document("requests", request_id)
    if not request_doc:
        return jsonify({"status": "error", "message": "Request not found"}), 404

    short_id = request_doc.get('shortId')
    if not short_id:
        return jsonify({"status": "error", "message": "Short ID not found in request"}), 400

    try:

        short_doc = firebase_services.get_document("shorts", short_id)
        if not short_doc:
            return jsonify({"status": "error", "message": "Short document not found"}), 404

        def update_progress(progress):
            firebase_services.update_document("shorts", short_id, {"update_progress": progress})
            firebase_services.update_document("requests", request_id, {"progress": progress})

        def update_message(message):
            firebase_services.update_document("shorts", short_id, {
                "progress_message": message,
                "last_updated": firestore.firestore.SERVER_TIMESTAMP
            })
            firebase_services.update_message(request_id, message)

        auto_generate = short_doc.get('auto_generate', False)

        update_message("Retrieved the document")
        firebase_services.update_document("shorts", short_id, {"pending_operation": True})
        update_progress(20)
        valid_short, error_message = parse_and_verify_short(short_doc)

        if not valid_short:
            update_message(f"Invalid short document: {error_message}")
            firebase_services.update_document("shorts", short_id, {
                "pending_operation": False,
                "auto_generate": False,
            })
            return jsonify({
                "status": "error",
                "data": {
                    "request_id": request_id,
                    "short_id": short_id,
                    "error": error_message
                },
                "message": "Failed to generate A-roll"
            }), 400

        # Parse bounding boxes
        bounding_boxes = json.loads(short_doc.get('bounding_boxes', '{}'))
        box_types = short_doc.get('box_type', [])

        # Prepare input for VideoCropper
        input_video_path = short_doc.get('short_clipped_video')
        if not input_video_path:
            raise ValueError("No input video path found in the short document")

        # Download the input video to a temporary file
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_input_file:
            firebase_services.download_file(input_video_path, temp_input_file.name)
            temp_input_path = temp_input_file.name

        update_message("Starting video cropping")
        update_progress(40)

        # Create VideoCropper instance
        video_cropper = VideoCropper(
            input_video_path=temp_input_path,
            bounding_boxes=bounding_boxes,
            frame_types=box_types
        )

        # Crop the video
        output_path = video_cropper.crop_video()

        update_message("Video cropping completed")
        update_progress(80)

        update_message("Creating Updated short audio file")
        generate_test_audio_for_short(request_id)  # Assuming this function has been updated to use request_id
        update_message("Adding audio now")
        short_doc = firebase_services.get_document("shorts", short_id)

        audio_path = firebase_services.download_file_to_temp(short_doc['temp_audio_file'], short_doc['temp_audio_file'].split(".")[-1])
        output_path = add_audio_to_video(output_path, audio_path)

        # Upload the cropped video to Firebase Storage
        destination_blob_name = f"shorts/{short_id}/a_roll.mp4"
        firebase_services.upload_file_from_temp(output_path, destination_blob_name)

        update_message("A-roll uploaded to storage")
        update_progress(100)

        firebase_services.update_document("shorts", short_id, {
            "short_a_roll": destination_blob_name,
            "pending_operation": False,
        })

        # Clean up temporary files
        os.remove(temp_input_path)
        video_cropper.clean_up(output_path)

        update_message("A-roll generation completed successfully")


        if auto_generate:
            firebase_services.create_short_request(
                "v1/create-cropped-video",
                short_id,
                request_doc.get('uid', "SERVER REQUEST")
            )

        return jsonify({
            "status": "success",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
                "a_roll_path": destination_blob_name,
            },
            "message": "Successfully generated and uploaded A-roll"
        }), 200

    except Exception as e:
        error_message = f"Failed to generate A-roll: {str(e)}"
        firebase_services.update_document("shorts", short_id, {
            "pending_operation": False,
            "auto_generate": False,
        })
        return jsonify({
            "status": "error",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
                "error": str(e)
            },
            "message": error_message
        }), 500
