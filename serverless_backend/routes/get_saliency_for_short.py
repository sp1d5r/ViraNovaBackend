from firebase_admin import firestore
from flask import Blueprint, jsonify
from serverless_backend.services.firebase import FirebaseService
import requests
import json
import os
from datetime import datetime

short_saliency = Blueprint("get_saliency_for_short", __name__)

@short_saliency.route("/v1/get_saliency_for_short/<request_id>", methods=['GET'])
def get_saliency_for_short(request_id):
    firebase_service = FirebaseService()
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

        short_video_path = short_document.get('short_clipped_video')

        if short_video_path is None:
            error_message = "No short video path found"
            update_message(error_message)
            firebase_service.update_document("shorts", short_id, {"pending_operation": False})
            return jsonify({
                "status": "error",
                "data": {
                    "request_id": request_id,
                    "short_id": short_id,
                    "error": error_message,
                },
                "message": "Failed to generate saliency for video"
            }), 400

        update_message("Loading video into temp locations")
        update_progress(20)

        url = os.getenv("SALIENCY_ENDPOINT_ADDRESS")
        payload = {"short_id": short_id}
        headers = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Authorization": "Bearer " + os.getenv("SALIENCY_BEARER_TOKEN") + "==",
            "Connection": "keep-alive",
            "Content-Type": "application/json"
        }

        response = requests.request("POST", url,
                                    headers=headers,
                                    data=json.dumps(payload)
                                    )

        update_message("Saliency generation completed")
        update_progress(100)

        firebase_service.create_short_request(
            "v1/determine-boundaries",
            short_id,
            request_doc.get('uid', 'SERVER REQUEST')
        )

        return jsonify({
            "status": "success",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
                "saliency_type": "Saliency Model",
                "ai-endpoint-response": str(response.content)
            },
            "message": "Generated saliency for video"
        }), 200

    except Exception as e:
        error_message = f"Failed to generate saliency for video: {str(e)}"
        update_message(error_message)
        firebase_service.update_document("shorts", short_id, {"pending_operation": False})
        return jsonify({
            "status": "error",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
                "error": str(e),
            },
            "message": error_message
        }), 500
