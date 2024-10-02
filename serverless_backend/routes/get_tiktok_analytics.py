from datetime import datetime
from flask import Blueprint, jsonify
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.tiktok_analytics import TikTokAnalytics
from serverless_backend.services.verify_video_document import parse_and_verify_short

tiktok_analytics = Blueprint("tiktok_analytics", __name__)

@tiktok_analytics.route("/v1/collect-tiktok-data/<short_id>/<task_runner_id>", methods=['GET'])
def collect_tiktok_data(short_id, task_runner_id):
    try:
        firebase_service = FirebaseService()
        tiktok_analytics = TikTokAnalytics()
        short_document = firebase_service.get_document("shorts", short_id)
        uid = short_document.get("uid", "")

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
                "shortId": short_id,
                "videoId": video_id,
                "tiktokLink": tiktok_link,
                "taskResultId": task_runner_id,
                "uid": uid,
            }

            tiktok_video_analytics = tiktok_analytics.get_tiktok_video_details(tiktok_link)

            task['videoAnalytics'] = tiktok_video_analytics
            task['taskTime'] = datetime.now()

            # Update short document with latest analytics
            latest_analytics = {
                "views": tiktok_video_analytics[0]['playCount'],
                "likes": tiktok_video_analytics[0]['diggCount'],
                "shares": tiktok_video_analytics[0]['shareCount'],
                "comments": tiktok_video_analytics[0]['commentCount'],
                "last_updated": datetime.now()
            }

            firebase_service.update_document("shorts", short_id, latest_analytics)

            # Collect comments if there's more than one
            if tiktok_video_analytics[0]['commentCount'] > 1:
                comments = tiktok_analytics.get_tiktok_comments(tiktok_link, tiktok_video_analytics[0]['commentCount'])
                if comments:
                    for comment in comments:
                        comment_data = {
                            "text": comment["text"],
                            "diggCount": comment["diggCount"],
                            "replyCommentTotal": comment["replyCommentTotal"],
                            "createTime": datetime.now(),
                            "createTimeISO": datetime.fromisoformat(comment["createTimeISO"].rstrip('Z')),
                            "uniqueId": comment["uniqueId"],
                            "comment_uid": comment["uid"],
                            "comment_cid": comment["cid"],
                            "avatarThumbnail": comment["avatarThumbnail"],
                            "shortId": short_id,
                            "uid": uid,
                        }
                        firebase_service.upsert_document("comments", comment['cid'], comment_data)

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


