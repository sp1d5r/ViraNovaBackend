import tempfile
import json
from datetime import datetime

from firebase_admin import firestore
from flask import Blueprint, jsonify

from serverless_backend.services.b_roll_editor.b_roll_editor_service import BRollEditorService
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.verify_video_document import parse_and_verify_short

generate_b_roll = Blueprint("generate_b_roll", __name__)

@generate_b_roll.route("/v1/generate-b-roll/<request_id>", methods=['GET'])
def generate_b_roll_short(request_id):
    firebase_services = FirebaseService()
    try:
        request_doc = firebase_services.get_document("requests", request_id)
        if not request_doc:
            return jsonify({"status": "error", "message": "Request not found"}), 404

        short_id = request_doc.get('shortId')
        if not short_id:
            return jsonify({"status": "error", "message": "Short ID not found in request"}), 400

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
                "message": "Failed to generate b-roll"
            }), 400

        if "b_roll_tracks" not in short_doc:
            update_message("No B Roll Tracks in document")
            firebase_services.update_document("shorts", short_id, {
                "pending_operation": False,
                "auto_generate": False,
            })
            return jsonify({
                "status": "error",
                "data": {
                    "request_id": request_id,
                    "short_id": short_id,
                    "error": "No B Roll Tracks in document..."
                },
                "message": "Failed to generate b-roll"
            }), 400

        update_message("Located B Roll")

        if "short_a_roll" not in short_doc:
            update_message("No A Roll in short document")
            firebase_services.update_document("shorts", short_id, {
                "pending_operation": False,
                "auto_generate": False,
            })
            return jsonify({
                "status": "error",
                "data": {
                    "request_id": request_id,
                    "short_id": short_id,
                    "error": "No A Roll in short document..."
                },
                "message": "Failed to generate b-roll"
            }), 400

        update_message("Located A Roll")

        b_roll_tracks = json.loads(short_doc['b_roll_tracks'])
        a_roll_location = short_doc['short_a_roll']

        update_message("Downloading A Roll")
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_input_file:
            firebase_services.download_file(a_roll_location, temp_input_file.name)
            temp_input_path = temp_input_file.name

        update_message("Editing Video...")

        fps = short_doc.get('fps', 30)

        b_roll_service = BRollEditorService(firebase_services, fps)
        edited_video_path = b_roll_service(temp_input_path, b_roll_tracks, update_progress)
        update_message("Complete!")

        update_message("Uploading new video...")
        video_with_b_roll_blob = f"shorts/{short_id}/b_roll.mp4"
        firebase_services.upload_file_from_temp(edited_video_path, video_with_b_roll_blob)
        update_message("Finished!")

        firebase_services.update_document(
            "shorts",
            short_id,
            {
                "pending_operation": False,
                "short_b_roll": video_with_b_roll_blob
            }
        )

        if auto_generate:
            firebase_services.update_document(
                "shorts",
                short_id,
                {
                    "short_status": "Preview Video",
                }
            )

        update_message("B-roll generation completed successfully")

        return jsonify({
            "status": "success",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
                "video_with_b_roll": video_with_b_roll_blob
            },
            "message": "Successfully generated b-roll"
        }), 200

    except Exception as e:
        error_message = f"Failed to generate b-roll: {str(e)}"
        update_message(error_message)
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
