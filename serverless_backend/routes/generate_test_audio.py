from io import BytesIO
import random

from firebase_admin import firestore
from flask import Blueprint, jsonify
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.handle_operations_from_logs import handle_operations_from_logs
from pydub import AudioSegment
from datetime import datetime

from serverless_backend.services.parse_segment_words import parse_segment_words
from serverless_backend.services.verify_video_document import parse_and_verify_short, parse_and_verify_video, parse_and_verify_segment

generate_test_audio = Blueprint("generate_test_audio", __name__)


@generate_test_audio.route("/v1/generate-test-audio/<request_id>", methods=['GET'])
def generate_test_audio_for_short(request_id, function_called=False):
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
        firebase_service.update_message(request_id, "Test audio generation process initiated")

        def update_progress(progress):
            firebase_service.update_document("shorts", short_id, {"update_progress": progress})
            firebase_service.update_document("requests", request_id, {"progress": progress})

        def update_message(message):
            firebase_service.update_document("shorts", short_id, {
                "progress_message": message,
                "last_updated": firestore.firestore.SERVER_TIMESTAMP
            })
            firebase_service.update_message(request_id, message)

        auto_generate = short_document.get('auto_generate', False)

        is_valid_document, error_message = parse_and_verify_short(short_document)
        if not is_valid_document:
            update_message(f"Invalid short document: {error_message}")
            return jsonify({
                "status": "error",
                "data": {"request_id": request_id, "short_id": short_id, "error": error_message},
                "message": "Failed to generate audio for clip"
            }), 400

        firebase_service.update_document('shorts', short_id, {'temp_audio_file': "Loading..."})
        firebase_service.update_document("shorts", short_id, {"pending_operation": True})

        update_message("Collected Short Document")
        logs = short_document['logs']
        update_progress(20)

        video_id = short_document.get('video_id')
        if not video_id:
            firebase_service.update_document("shorts", short_id, {
                "pending_operation": False,
                "auto_generate": False
            })
            update_message("No video id in short")
            return jsonify({
                "status": "error",
                "data": {"request_id": request_id, "short_id": short_id, "error": "No video id in short"},
                "message": "Failed to generate audio for clip"
            }), 404

        video_document = firebase_service.get_document('videos', video_id)
        is_valid_document, error_message = parse_and_verify_video(video_document)

        update_progress(40)
        if not is_valid_document:
            update_message("Not related to an original video... Contact someone...")
            firebase_service.update_document("shorts", short_id, {
                "pending_operation": False,
                "auto_generate": False
            })
            return jsonify({
                "status": "error",
                "data": {"request_id": request_id, "short_id": short_id, "error": error_message},
                "message": "Failed to generate audio for clip"
            }), 400
        else:
            update_message("Collected video document")

        audio_file = video_document['audio_path']

        segment_document = firebase_service.get_document('topical_segments', short_document['segment_id'])
        is_valid_document, error_message = parse_and_verify_segment(segment_document)

        if not is_valid_document:
            update_message("Not related to a segment... Contact someone...")
            firebase_service.update_document("shorts", short_id, {
                "pending_operation": False,
                "auto_generate": False
            })
            return jsonify({
                "status": "error",
                "data": {"request_id": request_id, "short_id": short_id, "error": error_message},
                "message": "Failed to generate audio for clip"
            }), 400
        else:
            update_message("Collected segment document")

        try:
            segment_document_words = parse_segment_words(segment_document)
        except ValueError as e:
            update_message(f"Error parsing segment words: {str(e)}")
            firebase_service.update_document("shorts", short_id, {
                "pending_operation": False,
                "auto_generate": False
            })
            return jsonify({
                "status": "error",
                "data": {"request_id": request_id, "short_id": short_id, "error": str(e)},
                "message": "Failed to parse segment words"
            }), 400

        update_message("Read Segment Words")
        words_to_handle = handle_operations_from_logs(logs, segment_document_words)
        words_to_handle = [
            {**word, 'end_time': min(word['end_time'], words_to_handle[i + 1]['start_time'])}
            if i + 1 < len(words_to_handle) else word
            for i, word in enumerate(words_to_handle)
        ]

        update_progress(60)
        update_message("Download Audio File to Memory")
        audio_stream = firebase_service.download_file_to_memory(audio_file)
        update_message("Create temporary audio file")
        audio_data = AudioSegment.from_file_using_temporary_files(audio_stream)

        combined_audio = AudioSegment.silent(duration=0)
        total_length = 0
        progress = 60

        for word in words_to_handle:
            start_time = int(word['start_time'] * 1000)
            end_time = int(word['end_time'] * 1000)
            segment_length = end_time - start_time
            total_length += segment_length
            segment = audio_data[start_time:end_time]
            combined_audio += segment
            progress_update = random.uniform(progress - 0.02 * progress, progress + 0.02 * progress)
            progress = min(progress_update, 98)
            update_progress(progress)
            update_message(f"Appended segment from {start_time} to {end_time}, segment length: {segment_length}, total expected length: {total_length}")

        update_message(f"Final combined length (from segments): {total_length}")
        update_message(f"Actual combined audio length: {len(combined_audio)}")

        update_message("Loading the bytes stream")
        byte_stream = BytesIO()
        combined_audio.export(byte_stream, format='mp4')

        update_message(f"New combined audio length: {len(combined_audio)}")

        new_blob_location = 'temp-audio/' + "".join(audio_file.split("/")[1:])

        byte_stream.seek(0)
        file_bytes = byte_stream.read()
        firebase_service.upload_audio_file_from_memory(new_blob_location, file_bytes)

        update_message("Uploaded Result")
        update_progress(100)

        if auto_generate:
            firebase_service.update_document("shorts", short_id, {
                'temp_audio_file': new_blob_location,
                "pending_operation": False,
            })

        firebase_service.update_document("shorts", short_id, {
            'temp_audio_file': new_blob_location,
            "pending_operation": False,
        })

        update_message("Test audio generation completed successfully")

        if auto_generate and not function_called:
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
                "temp_audio_location": new_blob_location,
            },
            "message": "Successfully generated audio for clip"
        }), 200

    except Exception as e:
        firebase_service.update_document("shorts", short_id, {
            "pending_operation": False,
            "auto_generate": False
        })
        update_message(f"Test audio generation failed: Unexpected error - {str(e)}")
        return jsonify({
            "status": "error",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
                "error": str(e)
            },
            "message": "Failed to generate audio for clip"
        }), 500