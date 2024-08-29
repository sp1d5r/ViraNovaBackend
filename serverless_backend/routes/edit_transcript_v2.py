from flask import Blueprint, jsonify
from firebase_admin import firestore
from datetime import datetime
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.verify_video_document import parse_and_verify_short
from serverless_backend.services.parse_segment_words import parse_segment_words
from serverless_backend.services.langchain_chains.edit_transcript.find_hook_chain import hook_chain
from serverless_backend.services.langchain_chains.edit_transcript.transcript_boundaries_chain import transcript_boundaries_chain
from serverless_backend.services.langchain_chains.edit_transcript.unnecessary_segments_chain import unnecessary_segments_chain

edit_transcript_v2 = Blueprint("edit_transcript_v2", __name__)

@edit_transcript_v2.route("/v2/temporal-segmentation/<request_id>", methods=['GET'])
def perform_temporal_segmentation_v2(request_id):
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
                "message": "Temporal segmentation v2 process initiated",
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
            firebase_service.update_message(request_id, "Temporal segmentation v2 failed: Invalid short document")
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
            firebase_service.update_document("requests", request_id, {"progress": progress})

        def update_message(message):
            firebase_service.update_document('shorts', short_id, {
                'progress_message': message,
                'last_updated': firestore.firestore.SERVER_TIMESTAMP
            })
            firebase_service.update_message(request_id, message)

        update_message("Starting temporal segmentation v2")
        update_progress(0)

        # Initialize logs
        logs = short_document.get('logs', [])

        # Parse segment words
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

        update_message("Converted segment words to working format")
        update_progress(10)

        short_idea = short_document['short_idea']
        transcript = " ".join([f"({i}) {word['word']}" for i, word in enumerate(words)])

        # Step 1: Determine transcript boundaries
        update_message("Determining transcript boundaries")
        boundaries = transcript_boundaries_chain.invoke({"transcript": transcript, "short_idea": short_idea})
        update_progress(30)

        # Apply boundaries
        for i in range(len(words)):
            if i < boundaries.start_index or i > boundaries.end_index:
                words[i]['isKept'] = False

        logs.append({
            "type": "delete",
            "start_index": 0,
            "end_index": boundaries.start_index - 1,
            "time": datetime.now(),
            "message": f"Removed content before index {boundaries.start_index}"
        })
        logs.append({
            "type": "delete",
            "start_index": boundaries.end_index + 1,
            "end_index": len(words) - 1,
            "time": datetime.now(),
            "message": f"Removed content after index {boundaries.end_index}"
        })

        # Step 2: Delete unnecessary segments
        update_message("Identifying and removing unnecessary segments")
        kept_transcript = " ".join([f"({i}) {word['word']}" for i, word in enumerate(words) if word['isKept']])
        unnecessary = unnecessary_segments_chain.invoke({"transcript": kept_transcript, "short_idea": short_idea})
        update_progress(60)

        for start, end in unnecessary.segments:
            for i in range(start, end + 1):
                if i < len(words):
                    words[i]['isKept'] = False
            logs.append({
                "type": "delete",
                "start_index": start,
                "end_index": end,
                "time": datetime.now(),
                "message": f"Removed unnecessary segment from index {start} to {end}"
            })

        # Step 3: Find the hook
        update_message("Finding the hook")
        final_transcript = " ".join([f"({i}) {word['word']}" for i, word in enumerate(words) if word['isKept']])
        hook = hook_chain.invoke({"transcript": final_transcript, "short_idea": short_idea})
        update_progress(90)

        # Generate lines from remaining words
        kept_words = [word for word in words if word['isKept']]
        adjusted_words = adjust_timestamps(kept_words)
        lines = generate_lines(adjusted_words)

        # Update short document
        firebase_service.update_document("shorts", short_id, {
            "lines": lines,
            "logs": logs,
            "hook_start": hook.start_index,
            "hook_end": hook.end_index,
            "pending_operation": False,
            "short_status": "Clipping Complete"
        })

        update_message("Temporal segmentation v2 completed successfully")
        update_progress(100)

        if auto_generate:
            firebase_service.create_short_request(
                "v1/generate-test-audio",
                short_id,
                request_doc.get('uid', 'SERVER REQUEST')
            )

        return jsonify({
            "status": "success",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
            },
            "message": "Successfully processed temporal segmentation v2"
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "data": {
                "request_id": request_id,
                "error": str(e)
            },
            "message": "Failed to process temporal segmentation v2"
        }), 500

def adjust_timestamps(words):
    if not words:
        return []

    adjusted_words = []
    cumulative_deleted_duration = 0
    previous_end_time = words[0]['start_time']

    for word in words:
        # Calculate the gap between this word and the previous one
        gap = word['start_time'] - previous_end_time

        # If there's a gap, it means words were deleted
        if gap > 0:
            cumulative_deleted_duration += gap

        adjusted_word = word.copy()
        adjusted_word['start_time'] = word['start_time'] - words[0]['start_time'] - cumulative_deleted_duration
        adjusted_word['end_time'] = word['end_time'] - words[0]['start_time'] - cumulative_deleted_duration

        adjusted_words.append(adjusted_word)
        previous_end_time = word['end_time']

    return adjusted_words

def generate_lines(words, max_words_per_line=3):
    lines = []
    current_line = {"words": [], "y_position": 0}  # Starting y_position, adjust as needed

    for i, word in enumerate(words):
        current_line["words"].append(word)

        # Check if we need to start a new line
        if len(current_line["words"]) == max_words_per_line or i == len(words) - 1:
            # Set the end time of the current line
            current_line["end_time"] = word["end_time"]

            # If there's a next word, adjust the current line's end time and last word's end time
            if i + 1 < len(words):
                next_word = words[i + 1]
                new_end_time = min(current_line["end_time"], next_word["start_time"])

                # Adjust the last word's end time
                current_line["words"][-1]["end_time"] = new_end_time
                current_line["end_time"] = new_end_time

            lines.append(current_line)

            # Start a new line
            if i + 1 < len(words):
                current_line = {
                    "words": [],
                    "y_position": current_line["y_position"] + 40,  # Adjust vertical spacing as needed
                    "start_time": words[i + 1]["start_time"]
                }

    # Ensure each line has a start_time (use the first word's start_time)
    for line in lines:
        if "start_time" not in line:
            line["start_time"] = line["words"][0]["start_time"]

    return lines