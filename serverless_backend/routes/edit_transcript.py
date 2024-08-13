import uuid
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
@edit_transcript.route("/v1/temporal-segmentation/<short_id>", methods=['GET'])
def perform_temporal_segmentation(short_id):
    firebase_service = FirebaseService()
    try:
        short_document = firebase_service.get_document("shorts", short_id)
        auto_generate = False

        if "auto_generate" in short_document.keys():
            auto_generate = short_document['auto_generate']

        is_valid_document, error_message = parse_and_verify_short(short_document)

        firebase_service.update_document("shorts", short_id, {"pending_operation": True})

        logs = [{
            "time": datetime.now(),
            "message": "Beginning Editing...",
            "type": "message"
        }]

        print(short_document)

        def update_logs(log):
            logs.append(log)
            firebase_service.update_document('shorts', short_id, {'logs': logs})

        if is_valid_document:
            print("Here")
            transcript = short_document['transcript']
            transcript_words = transcript.split(" ")
            words_with_index = [(index, word) for index, word in enumerate(transcript_words)]
            short_idea = short_document['short_idea']

            error_count = 0
            MAX_ERROR_LIMIT = 5

            print(f"error_count {error_count}, max limit: {short_document}")

            while error_count < MAX_ERROR_LIMIT:
                print("Began loop!")
                try:
                    update_logs({
                        "time": datetime.now(),
                        "title": "Chain Operation",
                        "message": "Checking if the transcript needs to be edited.",
                        "type": "message"
                    })

                    requires_cropping_uuid = uuid.uuid4()
                    does_transcript_require_cropping = requires_cropping_chain.invoke(
                        {"transcript": " ".join([f"{i[1]}" for i in words_with_index if i[0] >= 0]), "short_idea": short_idea},
                        config={"run_id": requires_cropping_uuid, "metadata": {"short_id": short_id}}
                    )

                    update_logs({
                        "time": datetime.now(),
                        "title": "Chain Operation",
                        "message": f"CHAIN: Does the transcript need to be cropped = {does_transcript_require_cropping.requires_cropping}",
                        "type": "message",
                    })

                    update_logs({
                        "time": datetime.now(),
                        "message": f"CHAIN: Explanation: {does_transcript_require_cropping.explanation}",
                        "type": "message",
                        "run_id": str(requires_cropping_uuid),
                    })

                    if does_transcript_require_cropping.requires_cropping:
                        update_logs({
                            "time": datetime.now(),
                            "message": "CHAIN: Determining where to crop...",
                            "type": "message"
                        })

                        delete_operation_uuid = uuid.uuid4()
                        transcript_delete_operation = delete_operation_chain.invoke(
                            {"transcript": " ".join([f"({i[0]}) {i[1]}" for i in words_with_index]),
                             "short_idea": short_idea},
                            config={"run_id": delete_operation_uuid, "metadata": {"short_id": short_id}}
                        )

                        update_logs({
                            "time": datetime.now(),
                            "message":f"CHAIN: Deleting between ({transcript_delete_operation.start_index} - {transcript_delete_operation.end_index}). Explanation: {transcript_delete_operation.explanation}",
                            "type": "delete",
                            "start_index": transcript_delete_operation.start_index,
                            "end_index": transcript_delete_operation.end_index,
                            "run_id": str(transcript_delete_operation),
                        })


                        words_with_index = delete_operation(
                            words_with_index=words_with_index,
                            start_index=transcript_delete_operation.start_index,
                            end_index=transcript_delete_operation.end_index
                        )

                        update_logs({
                            "time": datetime.now(),
                            "message": "CHAIN: Deleted transcript section.",
                            "type": "message"
                        })


                        if len([i for i in words_with_index if i[0] > -1]) < 70:
                            update_logs({
                                "time": datetime.now(),
                                "message": "CHAIN: Transcript has gotten met minimum word limit..",
                                "type": "success"
                            })
                            break
                    else:
                        update_logs({
                            "time": datetime.now(),
                            "message": "CHAIN: Transcript editing complete!",
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

            if error_count >= MAX_ERROR_LIMIT:
                update_logs({
                    "time": datetime.now(),
                    "message": "CHAIN: Transcript editing complete!",
                    "type": "success"
                })
                firebase_service.update_document('shorts', short_id, {'short_status': "Clipping Failed"})

            firebase_service.update_document("shorts", short_id, {"pending_operation": False})

            if auto_generate:
                firebase_service.update_document("shorts", short_id, {
                    'short_status': "Generate Audio"
                })

            return jsonify(
            {
                "status": "success",
                "data": {
                    "short_id": short_id,
                    "errors": error_count,
                    "maximum_errors_allowed": MAX_ERROR_LIMIT,
                    "logs": logs
                },
                "message": "Successfully edited transcript"
            }), 200
        else:
            firebase_service.update_document("shorts", short_id, {
                "pending_operation": False,
                "auto_generate": False
            })
            return jsonify(
                {
                    "status": "error",
                    "data": {
                        "short_id": short_id,
                        "error": error_message
                    },
                    "message": "Failed to edit transcript"
                }), 400
    except Exception as e:
        firebase_service.update_document("shorts", short_id, {
            "pending_operation": False,
            "auto_generate": False
        })
        return jsonify(
            {
                "status": "error",
                "data": {
                    "short_id": short_id,
                    "error": str(e)
                },
                "message": "Failed to edit transcript"
            }), 400
