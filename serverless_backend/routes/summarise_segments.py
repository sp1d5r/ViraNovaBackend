from flask import Blueprint, jsonify

from serverless_backend.services.email.brevo_email_service import EmailService
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.open_ai import OpenAIService
from firebase_admin import auth

from serverless_backend.services.vector_db.ziliz import ZilizVectorDB
from serverless_backend.services.verify_video_document import parse_and_verify_video

summarise_segments = Blueprint("summarise_segments", __name__)


def get_user_email(uid):
    try:
        user = auth.get_user(uid)
        return user.email
    except Exception as e:
        print(f"Error fetching user data for UID {uid}: {str(e)}")
        return None


def get_unique_emails(video_document, firebase_service):
    unique_emails = set()

    if video_document.get('uid'):
        # Video is for a specific user
        uid = video_document['uid']
        user_email = get_user_email(uid)
        if user_email:
            unique_emails.add(user_email)
        else:
            print(f"No email found for user {uid}")
    elif video_document.get('channelId'):
        # Video is for a channel
        channel_id = video_document['channelId']
        user_documents = firebase_service.query_documents('userstrackingchannels', 'channelId', channel_id)
        for user_document in user_documents:
            uid = user_document.get('uid')
            user_email = get_user_email(uid)
            if user_email:
                unique_emails.add(user_email)
            else:
                print(f"No email found for user {uid}")

    return unique_emails


def notify_users(video_document, email_service, firebase_service):
    video_title = video_document.get('originalFileName') or video_document.get('videoTitle')
    unique_emails = get_unique_emails(video_document, firebase_service)

    for email in unique_emails:
        email_service.send_video_ready_notification(email, video_title, '')

@summarise_segments.route("/v1/summarise-segments/<video_id>", methods=['GET'])
def summarise_segments_for_transcript(video_id):
    try:
        # Access video document and verify existance
        firebase_service = FirebaseService()
        open_ai_service = OpenAIService()
        ziliz_vector_db = ZilizVectorDB()
        video_document = firebase_service.get_document("videos", video_id)
        is_valid_document, error_message = parse_and_verify_video(video_document)
        update_progress_message = lambda x: firebase_service.update_document('videos', video_id,
                                                                             {'progressMessage': x})
        update_progress = lambda x: firebase_service.update_document('videos', video_id,
                                                                     {'processingProgress': x})
        if is_valid_document:
            print("Valid document")
            update_progress(0)
            update_progress_message("Segmenting Topical Segments")
            segments = firebase_service.query_topical_segments_by_video_id(video_id)
            print(segments)
            update_progress_message("Retrieved Segments, Summarising...")
            previous_segment_summary = ""
            for index, segment in enumerate(segments):
                update_progress((index+1) / len(segments) * 100)
                summary = open_ai_service.get_segment_summary(segment['index'], segment['transcript'], previous_segment_summary)
                content_moderation = open_ai_service.extract_moderation_metrics(segment['transcript'])
                segment_summary = summary['segment_summary']
                previous_segment_summary = summary.get("new_combined_summary", previous_segment_summary)
                segment_title = summary.get('segment_title', "Unable to name segment")
                update_progress_message("Description: " + segment_summary[:20] + "...")
                firebase_service.update_document("topical_segments", segment["id"],
                                                 {
                                                    'segment_summary': segment_summary,
                                                    'segment_title': segment_title,
                                                    'segment_status': "Segment Summarised",
                                                    'flagged': content_moderation['flagged'],
                                                    "harassment": content_moderation["harassment"],
                                                    "harassment_threatening": content_moderation["harassment_threatening"],
                                                    "hate": content_moderation['hate'],
                                                    "hate_threatening": content_moderation["hate_threatening"],
                                                    "self_harm": content_moderation["self_harm"],
                                                    "self_harm_intent": content_moderation['self_harm_intent'],
                                                    "sexual": content_moderation['sexual'],
                                                    "sexual_minors": content_moderation['sexual_minors'],
                                                  })
                segment['segment_summary'] = segment_summary
                segment['segment_title'] = segment_title
                segment_text = ziliz_vector_db.generate_segment_text(segment)
                ziliz_vector_db.get_embedding_and_upload_to_segments(segment_text, segment['id'], segment['video_id'], video_document['channelId'])


            update_progress_message("Segments Summarised!")

            email_service = EmailService()
            notify_users(video_document, email_service, firebase_service)

            firebase_service.update_document("videos", video_id, {'status': 'Create TikTok Ideas'})
            return jsonify(
                {
                    "status": "success",
                    "data": {
                        "video_id": video_id,
                    },
                    "message": "Successfully summarised segments"
                }), 200
        else:
            return jsonify(
                {
                    "status": "error",
                    "data": {
                        "video_id": video_id,
                        "error": error_message
                    },
                    "message": "Failed to summarise segments"
                }), 400
    except Exception as e:
        return jsonify(
            {
                "status": "error",
                "data": {
                    "video_id": video_id,
                    "error": str(e)
                },
                "message": "Failed to summarise segments"
            }), 400