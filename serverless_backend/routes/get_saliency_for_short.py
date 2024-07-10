from flask import Blueprint, jsonify
from serverless_backend.services.firebase import FirebaseService
import requests
import json
import os
from datetime import datetime

short_saliency = Blueprint("get_saliency_for_short", __name__)

@short_saliency.route("/v1/get_saliency_for_short/<short_id>", methods=['GET'])
def get_saliency_for_short(short_id):
    try:
        firebase_service = FirebaseService()
        short_document = firebase_service.get_document("shorts", short_id)
        update_progress = lambda x: firebase_service.update_document("shorts", short_id, {"update_progress": x})
        update_message = lambda x: firebase_service.update_document("shorts", short_id, {"progress_message": x, "last_updated": datetime.now()})
        firebase_service.update_document("shorts", short_id, {"pending_operation": True})

        short_video_path = short_document['short_clipped_video']

        if short_video_path is None:
            firebase_service.update_document("shorts", short_id, {"pending_operation": False})
            return jsonify(
                {
                    "status": "error",
                    "data": {
                        "short_id": short_id,
                        "error": "No short video path found",
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
            "Authorization": "Basic " + os.getenv("SALIENCY_BEARER_TOKEN") + "=",
            "Connection": "keep-alive",
            "Content-Type": "application/json"
        }

        response = requests.request("POST", url,
                                    headers=headers,
                                    data=json.dumps(payload)
                                    )

        return jsonify(
                    {
                        "status": "success",
                        "data": {
                            "short_id": short_id,
                            "saliency_type": "Saliency Model",
                            "ai-endpoint-response": str(response.content)
                        },
                        "message": "Generated saliency for video"
                    }), 200
    except Exception as e:
        return jsonify(
            {
                "status": "error",
                "data": {
                    "short_id": short_id,
                    "error": str(e),
                },
                "message": "Failed to generate saliency for video"
            }), 400

