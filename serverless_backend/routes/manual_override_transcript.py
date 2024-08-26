from flask import Blueprint, jsonify, request
from firebase_admin import firestore

from serverless_backend.routes.edit_transcript import adjust_timestamps, generate_lines
from serverless_backend.services.firebase import FirebaseService
from datetime import datetime
import uuid

from serverless_backend.services.parse_segment_words import parse_segment_words

manual_override_transcript = Blueprint("manual_override_transcript", __name__)

@manual_override_transcript.route("/v1/manual-override-transcript/<request_id>", methods=['GET'])
def process_manual_override(request_id):
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

        segment_id = short_document.get('segment_id')
        segment_document = firebase_service.get_document("topical_segments", segment_id)
        if not segment_document:
            return jsonify({"status": "error", "message": "Segment document not found"}), 404

        # Update request log to indicate process initiation
        firebase_service.update_document("requests", request_id, {
            "logs": firestore.firestore.ArrayUnion([{
                "message": "Manual override process initiated",
                "timestamp": datetime.now()
            }])
        })

        firebase_service.update_document("shorts", short_id, {"pending_operation": True})

        def update_progress(progress):
            firebase_service.update_document('shorts', short_id, {'update_progress': progress})

        def update_message(message):
            firebase_service.update_document('shorts', short_id, {
                'progress_message': message,
                'last_updated': firestore.firestore.SERVER_TIMESTAMP
            })
            firebase_service.update_message(request_id, message)

        update_message("Starting manual override processing")
        update_progress(0)


        try:
            segment_words = parse_segment_words(segment_document)
        except ValueError as e:
            error_message = f"Error parsing segment words: {str(e)}"
            update_message(error_message)
            firebase_service.update_document("shorts", short_id, {"pending_operation": False})
            return jsonify({
                "status": "error",
                "data": {"request_id": request_id, "short_id": short_id, "error": error_message},
                "message": "Failed to parse segment words"
            }), 400

        # Convert parsed segment words to our working format
        words = [
            {
                "word": word['word'],
                "start_time": word['start_time'],
                "end_time": word['end_time'],
                "isKept": True
            }
            for word in segment_words
        ]

        # Get the original words from the short document
        logs = short_document.get('logs', [])

        # Process the words based on the logs
        for log in logs:
            if log['type'] == 'delete':
                for i in range(log['start_index'], log['end_index'] + 1):
                    if i < len(words):
                        words[i]['isKept'] = False
            elif log['type'] == 'undelete':
                for i in range(log['start_index'], log['end_index'] + 1):
                    if i < len(words):
                        words[i]['isKept'] = True

        update_progress(50)
        update_message("Processed transcript, generating lines")

        # Generate lines from remaining words
        kept_words = [word for word in words if word['isKept']]
        adjusted_words = adjust_timestamps(kept_words)
        lines = generate_lines(adjusted_words)


        update_progress(75)
        update_message("Generated lines, updating document")

        # Update short document with new words, lines, and transcript
        firebase_service.update_document("shorts", short_id, {
            "words": words,
            "lines": lines,
            "pending_operation": False
        })

        update_progress(100)
        update_message("Manual override completed successfully")

        return jsonify({
            "status": "success",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
            },
            "message": "Successfully processed manual override"
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "data": {
                "request_id": request_id,
                "error": str(e)
            },
            "message": "Failed to process manual override"
        }), 500
