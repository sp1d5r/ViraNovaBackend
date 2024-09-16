from flask import Blueprint, jsonify
from firebase_admin import firestore
from datetime import datetime
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.langchain_chains.wyr.theme_generator_chain import generate_themes
import uuid

generate_video_ideas = Blueprint("generate_video_ideas", __name__)

@generate_video_ideas.route("/v1/generate-video-ideas/<request_id>", methods=['GET'])
def perform_video_idea_generation(request_id):
    firebase_service = FirebaseService()
    try:
        request_doc = firebase_service.get_document("requests", request_id)
        if not request_doc:
            return jsonify({"status": "error", "message": "Request not found"}), 404

        niche_id = request_doc.get('nicheId')
        if not niche_id:
            return jsonify({"status": "error", "message": "Niche ID not found in request"}), 400

        niche_document = firebase_service.get_document("niches", niche_id)
        if not niche_document:
            return jsonify({"status": "error", "message": "Niche document not found"}), 404

        # Get the number of ideas to generate
        number_of_ideas = niche_document.get('numberOfIdeas', 3)  # Default to 3 if not specified

        # Update request log to indicate process initiation
        firebase_service.update_document("requests", request_id, {
            "logs": firestore.firestore.ArrayUnion([{
                "message": f"Video idea generation process initiated for {number_of_ideas} ideas",
                "timestamp": datetime.now()
            }])
        })

        def update_progress(progress):
            firebase_service.update_document("requests", request_id, {"progress": progress})

        def update_message(message):
            firebase_service.update_message(request_id, message)

        update_message(f"Starting video idea generation for {number_of_ideas} ideas")
        update_progress(0)

        niche_name = niche_document.get('name', '')
        prompt = niche_document.get('prompt', '')  # Get the prompt from the niche document

        update_message(f"Generating {number_of_ideas} themes for niche: {niche_name}")
        update_progress(50)

        # Generate themes using our chain
        generation_uuid = uuid.uuid4()
        theme_result = generate_themes(niche_name, prompt, number_of_ideas)

        update_progress(80)

        # Create a new document for each theme
        theme_ids = []
        for theme, explanation in zip(theme_result.themes, theme_result.explanations):
            theme_data = {
                "nicheId": niche_id,
                "theme": theme,
                "explanation": explanation,
                "createdAt": firestore.firestore.SERVER_TIMESTAMP,
                "requestId": request_id,
                "status": "created"
            }
            theme_id = firebase_service.add_document("wyr-themes", theme_data)
            theme_ids.append(theme_id)

        update_message(f"{len(theme_ids)} themes generated and stored successfully")
        update_progress(100)

        # Update the original request document with the new theme document IDs
        firebase_service.update_document("requests", request_id, {
            "wyr_theme_ids": theme_ids,
            "completed_at": firestore.firestore.SERVER_TIMESTAMP
        })

        firebase_service.update_document(
            "niches",
            niche_id,
            {
                "prompt": "",
                "numberOfIdeas": 1,
                "status": "completed",
            }
        )

        return jsonify({
            "status": "success",
            "data": {
                "request_id": request_id,
                "niche_id": niche_id,
                "wyr_theme_ids": theme_ids,
                "theme_count": len(theme_ids)
            },
            "message": f"Successfully generated {len(theme_ids)} video ideas"
        }), 200

    except Exception as e:
        update_message(f"Error: {str(e)}")
        return jsonify({
            "status": "error",
            "data": {
                "request_id": request_id,
                "error": str(e)
            },
            "message": "Failed to generate video ideas"
        }), 500