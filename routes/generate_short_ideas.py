import uuid

from flask import Blueprint, jsonify
from services.firebase import FirebaseService
from services.langchain_chains.idea_generator_chain import idea_generator_chain
from services.verify_video_document import parse_and_verify_video, parse_and_verify_segment

generate_short_ideas = Blueprint("generate_short_ideas", __name__)


@generate_short_ideas.route("/generate-short-ideas/<video_id>")
def generate_short_ideas_from_segments(video_id: str):
    try:
        firebase_service = FirebaseService()
        video_document = firebase_service.get_document("videos", video_id)
        is_valid_document, error_message = parse_and_verify_video(video_document)

        if is_valid_document:
            topical_segments = firebase_service.query_topical_segments_by_video_id(video_id)
            for segment in topical_segments:
                try:
                    if segment['flagged']:
                        continue

                    tiktok_idea_uuid = uuid.uuid4()
                    tiktok_idea = idea_generator_chain.invoke({'transcript': segment['transcript']}, config={"run_id": tiktok_idea_uuid, "metadata": {"video_id": video_id, "topical_segment_id": segment['id']}})

                    if tiktok_idea.tiktok_idea == '':
                        continue

                    firebase_service.update_document(
                        'topical_segments',
                        segment['id'],
                        {
                            'short_idea': tiktok_idea.tiktok_idea,
                            'short_idea_explanation': tiktok_idea.explanation,
                            'short_idea_run_id': str(tiktok_idea_uuid),
                            'segment_status': "TikTok Idea Generated"
                        })
                except Exception as e:
                    firebase_service.update_document(
                        'topical_segments',
                        segment['id'],
                        {'segment_status': f"Error: {str(e)}"}
                    )

            firebase_service.update_document('videos', video_id, {'status': "Clip Transcripts"})
            return jsonify(
                {
                    "status": "success",
                    "data": {
                        "video_id": video_id,
                    },
                    "message": "Successfully generated short ideas for video segments"
                }), 200
        else:
            return jsonify(
            {
                "status": "error",
                "data": {
                    "video_id": video_id,
                    "error": "Video Document is not valid"
                },
                "message": "Failed to generate short ideas for video segments"
            }), 400
    except Exception as e:
        return jsonify(
            {
                "status": "error",
                "data": {
                    "video_id": video_id,
                    "error": e
                },
                "message": "Failed to generate short ideas for video segments"
            }), 400


@generate_short_ideas.route("/generate-short-ideas-for-segment/<segment_id>")
def generate_short_ideas_for_segments(segment_id: str):
    try:
        firebase_service = FirebaseService()
        topical_segments_document = firebase_service.get_document("topical_segments", segment_id)
        is_valid_document, error_message = parse_and_verify_segment(topical_segments_document)

        if is_valid_document:
            if not topical_segments_document['flagged']:
                tiktok_idea_uuid = uuid.uuid4()
                tiktok_idea = idea_generator_chain.invoke(
                    {'transcript': topical_segments_document['transcript']},
                    config={"run_id": tiktok_idea_uuid,"metadata": {"segment_id": segment_id, "topical_segment_id": segment_id}})

                if tiktok_idea.tiktok_idea == '':
                    return "Failed"

                firebase_service.update_document(
                'topical_segments',
                segment_id,
                {
                    'short_idea': tiktok_idea.tiktok_idea,
                    'short_idea_explanation': tiktok_idea.explanation,
                    'short_idea_run_id': str(tiktok_idea_uuid),
                    'segment_status': "TikTok Idea Generated"
                })

                return jsonify(
                    {
                        "status": "success",
                        "data": {
                            "segment_id": segment_id,
                            "short_idea": tiktok_idea.tiktok_idea,
                            "explanation": tiktok_idea.explanation
                        },
                        "message": "Successfully generated short ideas for segment"
                    }), 200
            else:
                return jsonify(
                    {
                        "status": "error",
                        "data": {
                            "segment_id": segment_id,
                            "error": "This segment was flagged, and we are unable to generate a short for it."
                        },
                        "message": "Failed to generate short ideas for segment"
                    }), 200
        else:
            return jsonify(
                {
                    "status": "error",
                    "data": {
                        "segment_id": segment_id,
                        "error": "Segment Document is not valid"
                    },
                    "message": "Failed to generate short ideas for segment"
                }), 400
    except Exception as e:
        return jsonify(
            {
                "status": "error",
                "data": {
                    "segment_id": segment_id,
                    "error": e
                },
                "message": "Failed to generate short ideas for segment"
            }), 400
