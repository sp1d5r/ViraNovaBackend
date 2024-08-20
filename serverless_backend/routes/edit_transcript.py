from firebase_admin import firestore
from flask import Blueprint, jsonify
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.langchain_chains.crop_segment import requires_cropping_chain, delete_operation_chain
from serverless_backend.services.langchain_chains.title_generator_chain import title_generator_chain
from serverless_backend.services.verify_video_document import parse_and_verify_short
from serverless_backend.services.parse_segment_words import parse_segment_words
from datetime import datetime
import uuid

edit_transcript = Blueprint("edit_transcript", __name__)


@edit_transcript.route("/v1/temporal-segmentation/<request_id>", methods=['GET'])
def perform_temporal_segmentation(request_id):
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
                "message": "Temporal segmentation process initiated",
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
            firebase_service.update_message(request_id, "Temporal segmentation failed: Invalid short document")
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

        update_message("Starting temporal segmentation")
        update_progress(0)

        # Initialize logs
        logs = short_document.get('logs', [])

        # Parse segment words using the provided function
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
        error_count = 0
        MAX_ERROR_LIMIT = 5

        while error_count < MAX_ERROR_LIMIT:
            try:
                update_message("Checking if the transcript needs to be edited")
                update_progress(30 + (60 * error_count / MAX_ERROR_LIMIT))

                requires_cropping_uuid = uuid.uuid4()
                does_transcript_require_cropping = requires_cropping_chain.invoke(
                    {"transcript": " ".join([word['word'] for word in words if word['isKept']]),
                     "short_idea": short_idea},
                    config={"run_id": requires_cropping_uuid,
                            "metadata": {"short_id": short_id, "request_id": request_id}}
                )

                update_message(
                    f"Does the transcript need to be cropped = {does_transcript_require_cropping.requires_cropping}")

                if does_transcript_require_cropping.requires_cropping:
                    update_message("Determining where to crop")

                    delete_operation_uuid = uuid.uuid4()
                    transcript_delete_operation = delete_operation_chain.invoke(
                        {"transcript": " ".join(
                            [f"({index}) {word['word']}" for index, word in enumerate(words) if word['isKept']]),
                            "short_idea": short_idea},
                        config={"run_id": delete_operation_uuid,
                                "metadata": {"short_id": short_id, "request_id": request_id}}
                    )

                    update_message(
                        f"Deleting between indexes ({transcript_delete_operation.start_index} - {transcript_delete_operation.end_index}). Explanation: {transcript_delete_operation.explanation}")

                    # Perform delete operation on words
                    for index, word in enumerate(words):
                        if transcript_delete_operation.start_index <= index <= transcript_delete_operation.end_index:
                            word['isKept'] = False

                    # Update logs
                    logs.append({
                        "type": "delete",
                        "start_index": transcript_delete_operation.start_index,
                        "end_index": transcript_delete_operation.end_index,
                        "time": datetime.now(),
                        "message": f"Deleted content from index {transcript_delete_operation.start_index} to {transcript_delete_operation.end_index}"
                    })

                    update_message("Deleted transcript section")

                    if sum(1 for word in words if word['isKept']) < 70:
                        update_message("Transcript has met minimum word limit")
                        break
                else:
                    update_message("Transcript editing complete!")
                    firebase_service.update_document('shorts', short_id, {'short_status': "Clipping Complete"})
                    break
            except Exception as e:
                update_message(f"FAILED IN PIPELINE: {str(e)}")
                error_count += 1

        update_progress(90)

        # Generate lines from remaining words
        kept_words = [word for word in words if word['isKept']]
        adjusted_words = adjust_timestamps(kept_words)
        lines = generate_lines(adjusted_words)

        # Generate title
        final_transcript = " ".join([word['word'] for word in kept_words])
        title_result = title_generator_chain.invoke({
            "tiktok_idea": short_idea,
            "segment_transcript": final_transcript
        })

        # Update short document with new lines, logs, and title
        firebase_service.update_document("shorts", short_id, {
            "lines": lines,
            "logs": logs,
            "short_title_top": title_result.short_title_top,
            "short_title_bottom": title_result.short_title_bottom,
            "pending_operation": False
        })

        update_message(f"Generated title: {title_result.short_title_top} | {title_result.short_title_bottom}")
        update_progress(100)

        if auto_generate:
            firebase_service.create_short_request(
                "v1/generate-test-audio",
                short_id,
                request_doc.get('uid', 'SERVER REQUEST')
            )

        firebase_service.update_message(request_id, "Temporal segmentation completed successfully")

        return jsonify({
            "status": "success",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
                "errors": error_count,
                "maximum_errors_allowed": MAX_ERROR_LIMIT,
            },
            "message": "Successfully processed temporal segmentation"
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "data": {
                "request_id": request_id,
                "error": str(e)
            },
            "message": "Failed to process temporal segmentation"
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
                    "y_position": 0,  # Adjust vertical spacing as needed
                    "start_time": words[i + 1]["start_time"]
                }

    # Ensure each line has a start_time (use the first word's start_time)
    for line in lines:
        if "start_time" not in line:
            line["start_time"] = line["words"][0]["start_time"]

    return lines
