import uuid

from firebase_admin import firestore
from flask import Blueprint, jsonify
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.langchain_chains.crop_segment import requires_cropping_chain, delete_operation_chain
from serverless_backend.services.verify_video_document import parse_and_verify_short
from datetime import datetime

edit_transcript = Blueprint("edit_transcript", __name__)


# Route Functions
def delete_operation(words_with_index, start_index, end_index):
    # Find the position in the list for the start index
    start_position = None
    for position, (index, _) in enumerate(words_with_index):
        if index == start_index:
            start_position = position
            break

    if start_position is None:
        raise ValueError("Start index not found in the current list of words.")

    # Modify the list to clearly indicate deletions
    new_words_with_index = []
    for position, (index, word) in enumerate(words_with_index):
        if start_index <= index <= end_index:
            # Replace the word with a placeholder indicating deletion
            new_words_with_index.append((-1, word))
        else:
            new_words_with_index.append((index, word))

    return new_words_with_index

# Route
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
            # Update request log for error
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

        logs = [{
            "time": datetime.now(),
            "message": "Beginning Editing...",
            "type": "message"
        }]

        def update_logs(log):
            logs.append(log)
            firebase_service.update_document('shorts', short_id, {'logs': logs})

        def update_progress(progress):
            firebase_service.update_document('shorts', short_id, {'update_progress': progress})

        transcript = short_document['transcript']
        transcript_words = transcript.split(" ")
        words_with_index = [(index, word) for index, word in enumerate(transcript_words)]
        short_idea = short_document['short_idea']

        error_count = 0
        MAX_ERROR_LIMIT = 5

        while error_count < MAX_ERROR_LIMIT:
            try:
                update_logs({
                    "time": datetime.now(),
                    "message": "Checking if the transcript needs to be edited.",
                    "type": "message"
                })
                update_progress(10 + (90 * error_count / MAX_ERROR_LIMIT))

                requires_cropping_uuid = uuid.uuid4()
                does_transcript_require_cropping = requires_cropping_chain.invoke(
                    {"transcript": " ".join([f"{i[1]}" for i in words_with_index if i[0] >= 0]), "short_idea": short_idea},
                    config={"run_id": requires_cropping_uuid, "metadata": {"short_id": short_id, "request_id": request_id}}
                )

                update_logs({
                    "time": datetime.now(),
                    "message": f"Does the transcript need to be cropped = {does_transcript_require_cropping.requires_cropping}",
                    "type": "message",
                })

                if does_transcript_require_cropping.requires_cropping:
                    update_logs({
                        "time": datetime.now(),
                        "message": "Determining where to crop...",
                        "type": "message"
                    })

                    delete_operation_uuid = uuid.uuid4()
                    transcript_delete_operation = delete_operation_chain.invoke(
                        {"transcript": " ".join([f"({i[0]}) {i[1]}" for i in words_with_index]),
                         "short_idea": short_idea},
                        config={"run_id": delete_operation_uuid, "metadata": {"short_id": short_id, "request_id": request_id}}
                    )

                    update_logs({
                        "time": datetime.now(),
                        "message": f"Deleting between ({transcript_delete_operation.start_index} - {transcript_delete_operation.end_index}). Explanation: {transcript_delete_operation.explanation}",
                        "type": "delete",
                        "start_index": transcript_delete_operation.start_index,
                        "end_index": transcript_delete_operation.end_index,
                    })

                    words_with_index = delete_operation(
                        words_with_index=words_with_index,
                        start_index=transcript_delete_operation.start_index,
                        end_index=transcript_delete_operation.end_index
                    )

                    update_logs({
                        "time": datetime.now(),
                        "message": "Deleted transcript section.",
                        "type": "message"
                    })

                    if len([i for i in words_with_index if i[0] > -1]) < 70:
                        update_logs({
                            "time": datetime.now(),
                            "message": "Transcript has met minimum word limit.",
                            "type": "success"
                        })
                        break
                else:
                    update_logs({
                        "time": datetime.now(),
                        "message": "Transcript editing complete!",
                        "type": "success"
                    })
                    firebase_service.update_document('shorts', short_id, {'short_status': "Clipping Complete"})
                    break
            except Exception as e:
                update_logs({
                    "time": datetime.now(),
                    "message": f"FAILED IN PIPELINE: {str(e)}",
                    "type": "error"
                })
                error_count += 1

        update_progress(100)


        firebase_service.update_document("shorts", short_id, {"pending_operation": False})
        if auto_generate:
            firebase_service.create_short_request(
                "v1/generate-test-audio",
                short_id,
                request_doc.get('uid', 'SERVER REQUEST')

            )

        # Update request log for success
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