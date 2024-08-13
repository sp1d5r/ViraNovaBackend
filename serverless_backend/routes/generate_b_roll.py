import tempfile
import json
from datetime import datetime
from flask import Blueprint, jsonify

from serverless_backend.services.b_roll_editor.b_roll_editor_service import BRollEditorService
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.verify_video_document import parse_and_verify_short

generate_b_roll = Blueprint("generate_b_roll", __name__)

@generate_b_roll.route("/v1/generate-b-roll/<short_id>", methods=['GET'])
def generate_b_roll_short(short_id):
    firebase_services = FirebaseService()
    try:
        short_doc = firebase_services.get_document("shorts", short_id)
        update_progress = lambda x: firebase_services.update_document("shorts", short_id, {"update_progress": x})
        update_message = lambda x: firebase_services.update_document("shorts", short_id,
                                                                    {"progress_message": x, "last_updated": datetime.now()})

        auto_generate = False

        if "auto_generate" in short_doc.keys():
            auto_generate = short_doc['auto_generate']

        update_message("Retrieved the document")
        firebase_services.update_document("shorts", short_id, {"pending_operation": True})
        update_progress(20)
        valid_short, error_message = parse_and_verify_short(short_doc)

        if not valid_short:
            firebase_services.update_document("shorts", short_id, {
                "pending_operation": False,
                "auto_generate": False,
            })
            return jsonify(
                {
                    "status": "error",
                    "data": {
                        "short_id": short_id,
                        "error": error_message
                    },
                    "message": "Failed to generate b-roll"
                }), 400


        if not "b_roll_tracks" in short_doc:
            firebase_services.update_document("shorts", short_id, {
                "pending_operation": False,
                "auto_generate": False,
            })
            return jsonify(
                {
                    "status": "error",
                    "data": {
                        "short_id": short_id,
                        "error": "No B Roll Tracks in document..."
                    },
                    "message": "Failed to generate b-roll"
                }), 400

        update_message("Located B Roll")

        if not "short_a_roll" in short_doc:
            firebase_services.update_document("shorts", short_id, {
                "pending_operation": False,
                "auto_generate": False,
            })
            return jsonify(
                {
                    "status": "error",
                    "data": {
                        "short_id": short_id,
                        "error": "No A Roll in short document..."
                    },
                    "message": "Failed to generate b-roll"
                }), 400
        update_message("Located A Roll")

        b_roll_tracks = json.loads(short_doc['b_roll_tracks'])
        a_roll_location = short_doc['short_a_roll']

        update_message("Downloading A Roll")
        temp_input_path = ""
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

        return jsonify(
            {
                "status": "success",
                "data": {
                    "short_id": short_id,
                    "video_with_b_roll": video_with_b_roll_blob
                },
                "message": "Successfully to generate b-roll"
            }), 400

    except Exception as e:
        firebase_services.update_document("shorts", short_id, {
            "pending_operation": False,
            "auto_generate": False,
        })
        return jsonify(
            {
                "status": "error",
                "data": {
                    "short_id": short_id,
                    "error": str(e)
                },
                "message": "Failed to generate b-roll"
            }), 400