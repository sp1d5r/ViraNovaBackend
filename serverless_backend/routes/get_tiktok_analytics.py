from datetime import datetime
from flask import Blueprint, jsonify
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.tiktok_analytics import TikTokAnalytics
from serverless_backend.services.verify_video_document import parse_and_verify_short

tiktok_analytics = Blueprint("tiktok_analytics", __name__)

@tiktok_analytics.route("/v1/collect-tiktok-data/<short_id>", methods=['GET'])
def collect_tiktok_data(short_id):
    try:
        firebase_service = FirebaseService()
        tiktok_analytics = TikTokAnalytics()
        short_document = firebase_service.get_document("shorts", short_id)

        is_valid_document, error_message = parse_and_verify_short(short_document)
        if is_valid_document:
            if "tiktok_link" in short_document.keys():
                tiktok_link = short_document['tiktok_link']
            else:
                firebase_service.update_document("shorts", short_id, {"pending_operation": False})
                return jsonify(
                    {
                        "status": "error",
                        "data": {
                            "short_id": short_id,
                            "error": "No tiktok link in short."
                        },
                        "message": "Failed to collect tiktok analytics"
                    }), 404

            if "video_id" in short_document.keys():
                video_id = short_document['video_id']
            else:
                firebase_service.update_document("shorts", short_id, {"pending_operation": False})
                return jsonify(
                    {
                        "status": "error",
                        "data": {
                            "short_id": short_id,
                            "error": "No video id in short..."
                        },
                        "message": "Failed to collect tiktok analytics"
                    }), 404

            task = {
                "task_time": datetime.now(),
                "short_id": short_id,
                "video_id": video_id,
                "tiktok_link": tiktok_link
            }

            tiktok_video_analytics = tiktok_analytics.get_tiktok_video_details(tiktok_link)

            task['video_analytics'] = tiktok_video_analytics

            analytics_id = firebase_service.add_document("analytics", task)


            return jsonify(
                {
                    "status": "success",
                    "data": {
                        "short_id": short_id,
                        "analytics_id": analytics_id,
                    },
                    "message": "Successfully collected analytics for video."
                }), 200
        else:
            return jsonify(
                {
                    "status": "error",
                    "data": {
                        "short_id": short_id,
                        "error": error_message
                    },
                    "message": "Failed to collect tiktok analytics"
                }), 400
    except Exception as e:
        return jsonify(
            {
                "status": "error",
                "data": {
                    "short_id": short_id,
                    "error": str(e)
                },
                "message": "Failed to collect tiktok analytics"
            }), 400


