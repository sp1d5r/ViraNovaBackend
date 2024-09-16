from flask import Blueprint, jsonify
from firebase_admin import firestore
from datetime import datetime
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.langchain_chains.wyr.generate_options import generate_options

new_wyr_video = Blueprint("new_wyr_video", __name__)


@new_wyr_video.route("/v1/new-wyr-video/<request_id>", methods=['GET'])
def perform_new_wyr_video(request_id):
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

        idea_id = request_doc.get("ideaId")
        if not idea_id:
            return jsonify({"status": "error", "message": "Idea ID not found in request"}), 400

        idea_document = firebase_service.get_document("wyr-themes", idea_id)
        if not idea_document:
            return jsonify({"status": "error", "message": "Idea document not found"}), 404

        # Update request log to indicate process initiation
        firebase_service.update_document("requests", request_id, {
            "logs": firestore.firestore.ArrayUnion([{
                "message": f"New wyr video requested for idea: {idea_document.get('theme', 'UNKNOWN')}",
                "timestamp": datetime.now()
            }])
        })

        def update_progress(progress):
            firebase_service.update_document("requests", request_id, {"progress": progress})

        def update_message(message):
            firebase_service.update_message(request_id, message)

        update_message(f"Starting video generation")
        update_progress(0)

        # Generate multiple sets of options
        theme = idea_document.get('theme')
        explanation = idea_document.get('explanation')
        num_sets = 5  # Number of option sets to generate
        option_sets = []
        previous_options = set()

        for i in range(num_sets):
            update_progress((i + 1) * 20)  # Update progress (20% per set)
            update_message(f"Generating option set {i + 1} of {num_sets}")

            if i == num_sets - 1:
                specific_instructions = f"Don't include these options: {', '.join(previous_options)} - include a follow/like/comment CTA please." if previous_options else ""
            else:
                specific_instructions = f"Don't include these options: {', '.join(previous_options)}" if previous_options else ""

            option_set = generate_options(theme, explanation, specific_instructions)

            option_sets.append({
                "transcript": option_set.transcript,
                "option1": option_set.option1,
                "option2": option_set.option2,
                "option1_percentage": option_set.option1_percentage
            })

            previous_options.add(option_set.option1)
            previous_options.add(option_set.option2)

        # Create a new document to store the generated options
        new_wyr_video = {
            "nicheId": niche_id,
            "ideaId": idea_id,
            "theme": theme,
            "explanation": explanation,
            "optionSets": option_sets,
            "createdAt": datetime.now(),
            "updatedAt": datetime.now(),
            "uid": request_doc.get('uid', 'Unknown')
        }

        # Store the new document in Firestore
        new_wyr_video_id = firebase_service.add_document("wyr-videos", new_wyr_video)

        update_progress(100)
        update_message("Video options generated successfully")

        return jsonify({
            "status": "success",
            "data": {
                "request_id": request_id,
                "niche_id": niche_id,
                "idea_id": idea_id,
                "wyr_video_id": new_wyr_video_id
            },
            "message": f"Successfully generated new WYR Video options"
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