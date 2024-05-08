from flask import Blueprint, jsonify
from services.firebase import FirebaseService
from services.langchain_chains.idea_generator_chain import idea_generator_chain
from services.verify_video_document import parse_and_verify_video

generate_short_ideas = Blueprint("generate_short_ideas", __name__)


@generate_short_ideas.route("/generate-short-ideas/<video_id>")
def generate_short_ideas_from_segments(video_id: str):
    firebase_service = FirebaseService()
    video_document = firebase_service.get_document("videos", video_id)
    is_valid_document, error_message = parse_and_verify_video(video_document)

    if is_valid_document:
        topical_segments = firebase_service.query_topical_segments_by_video_id(video_id)
        for segment in topical_segments:
            try:
                tiktok_idea = idea_generator_chain.invoke({'transcript': segment['transcript']})
                if tiktok_idea.tiktok_idea == '':
                    continue

                firebase_service.update_document(
                    'topical_segments',
                    segment['id'],
                    {
                        'short_idea': tiktok_idea.tiktok_idea,
                        'short_idea_explanation': tiktok_idea.explanation,
                        'segment_status': "TikTok Idea Generated"
                    })
            except Exception as e:
                firebase_service.update_document(
                    'topical_segments',
                    segment['id'],
                    {'segment_status': f"Error: {str(e)}"}
                )

        firebase_service.update_document('videos', video_id, {'status': "Clip Transcripts"})
        return "Completed Segment Idea Extraction", 200
    else:
        return error_message, 404