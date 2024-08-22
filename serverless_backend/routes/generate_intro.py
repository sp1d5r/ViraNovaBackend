from flask import Blueprint, jsonify
from firebase_admin import firestore
from datetime import datetime
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.verify_video_document import parse_and_verify_short
from serverless_backend.services.langchain_chains.contextual_introduction.contextual_introduction_chain import context_chain
from serverless_backend.services.text_to_speech.eleven_labs_tts_service import generate_ai_voiceover
import os
import tempfile
from typing import Dict, Tuple

generate_intro = Blueprint("generate_intro", __name__)


def generate_contextual_intro(short_document: Dict, short_doc_id: str, update_progress, update_message) -> Tuple[str, str]:
    """
    Generate a contextual introduction for a Short document.

    :param short_document: The Short document containing transcript and other metadata
    :param short_doc_id: The ID of the short document
    :param update_progress: Function to update the progress
    :param update_message: Function to update the status message
    :return: Tuple of (local file path, intended blob path)
    """
    update_progress(10)
    update_message("Preparing transcript for contextual introduction generation")

    # Extract transcript from lines
    lines = short_document.get('lines', [])
    transcript = " ".join([word['word'] for line in lines for word in line['words'] if word.get('isKept', True)])

    short_idea = short_document.get('short_idea', '')
    short_idea_explanation = short_document.get('short_idea_explanation', '')

    update_progress(30)
    update_message("Generating contextual introduction")

    # Generate contextual introduction
    context_result = context_chain.invoke({
        "transcript": transcript,
        "short_idea": short_idea,
        "short_idea_justification": short_idea_explanation
    })

    update_progress(60)
    update_message("Contextual introduction generated, preparing for text-to-speech conversion")

    if context_result.needs_context:
        intro_transcript = context_result.intro_transcript

        # Generate audio file
        update_progress(80)
        update_message("Converting introduction to speech")

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            temp_filename = temp_file.name
            audio_path = generate_ai_voiceover(intro_transcript, temp_filename)

        if audio_path:
            update_progress(100)
            update_message("Contextual introduction audio generated successfully")
            # Return both the local file path and the intended blob path
            return temp_filename, f'intro_audio/{short_doc_id}/intro_audio.mp3'
        else:
            update_progress(100)
            update_message("Failed to generate audio for contextual introduction")
            if os.path.exists(temp_filename):
                os.unlink(temp_filename)
            return "", ""
    else:
        update_progress(100)
        update_message("No contextual introduction needed")
        return "", ""




@generate_intro.route("/v1/generate-intro/<request_id>", methods=['GET'])
def generate_intro_info(request_id):
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

        # Update request log to indicate process initiation
        firebase_service.update_document("requests", request_id, {
            "logs": firestore.firestore.ArrayUnion([{
                "message": "Contextual Intro Generated",
                "timestamp": datetime.now()
            }])
        })

        is_valid_document, error_message = parse_and_verify_short(short_document)
        if not is_valid_document:
            firebase_service.update_document("shorts", short_id, {
                "logs": firestore.firestore.ArrayUnion([{
                    "time": datetime.now(),
                    "message": f"Invalid short document: {error_message}",
                    "type": "error"
                }])
            })
            firebase_service.update_message(request_id, "Contextual Intro Failed: Invalid short document")
            return jsonify({
                "status": "error",
                "data": {
                    "request_id": request_id,
                    "short_id": short_id,
                    "error": error_message
                },
                "message": "Invalid short document"
            }), 400

        auto_generate = short_document.get('auto_generate', False)

        firebase_service.update_document("shorts", short_id, {"pending_operation": True})

        def update_progress(progress):
            firebase_service.update_document('shorts', short_id, {'update_progress': progress})

        def update_message(message):
            firebase_service.update_document('shorts', short_id, {
                'progress_message': message,
                'last_updated': firestore.firestore.SERVER_TIMESTAMP
            })
            firebase_service.update_message(request_id, message)

        local_audio_path, blob_path = generate_contextual_intro(short_document, short_id, update_progress,
                                                                update_message)

        if local_audio_path and blob_path:
            firebase_service.upload_file_from_temp(local_audio_path, blob_path)

            firebase_service.update_document("shorts", short_id, {
                "intro_audio_path": blob_path,
                "pending_operation": False,
                "short_status": "Intro Generated"
            })

            # Clean up the temporary file
            if os.path.exists(local_audio_path):
                os.unlink(local_audio_path)

        update_message("Temporal segmentation v2 completed successfully")
        update_progress(100)

        if auto_generate:
            firebase_service.create_short_request(
                "v1/create-short-video",
                short_id,
                request_doc.get('uid', 'SERVER REQUEST')
            )

        return jsonify({
            "status": "success",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
            },
            "message": "Successfully generated intro audio."
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "data": {
                "request_id": request_id,
                "error": str(e)
            },
            "message": "Failed to process generated intro audio"
        }), 500



