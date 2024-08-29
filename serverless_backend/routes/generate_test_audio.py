import os
import tempfile
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

        update_message("Starting audio processing")
        update_progress(20)

        video_document = firebase_service.get_document('videos', video_id)
        audio_file = video_document['audio_path']

        # Determine the input file extension from the original audio file
        _, input_extension = os.path.splitext(audio_file)
        if not input_extension:
            input_extension = '.mp4'  # Default to .mp4 if no extension is found

        # Download the entire file to a temporary location on disk
        with tempfile.NamedTemporaryFile(delete=False, suffix=input_extension) as temp_file:
            firebase_service.download_file(audio_file, temp_file.name)
            local_audio_path = temp_file.name

        update_message("Audio file downloaded to local storage")
        update_progress(40)
        print(local_audio_path)

        # Process audio in chunks
        combined_audio = AudioSegment.empty()
        audio = AudioSegment.from_file(local_audio_path, format=input_extension[1:])

        for i, word in enumerate(words_to_handle):
            start_time = int(word['start_time'] * 1000)
            end_time = int(word['end_time'] * 1000)

            segment = audio[start_time:end_time]
            combined_audio += segment

            progress = 40 + (i / len(words_to_handle) * 50)
            update_progress(progress)
            update_message(f"Processed segment {i + 1}/{len(words_to_handle)}")

        update_progress(90)
        update_message("Finalizing audio")

        # Export the combined audio as MP4
        new_blob_name = f'temp-audio/{short_id}_output.mp4'
        output_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        output_path = output_file.name
        combined_audio.export(output_path, format="mp4", codec="aac")

        # Upload the result
        firebase_service.upload_file_from_temp(output_path, new_blob_name)

        output_file.close()

        print(output_path)

        update_progress(100)
        update_message("Test audio generation completed successfully")

        firebase_service.update_document("shorts", short_id, {
            'temp_audio_file': new_blob_name,
            "pending_operation": False,
        })

        update_message("Test audio generation completed successfully")


        # Clean up
        os.unlink(local_audio_path)


        if auto_generate and not function_called:
            firebase_service.create_short_request(
                "v1/generate-intro",
                short_id,
                request_doc.get('uid', 'SERVER REQUEST')
            )

        return jsonify({
            "status": "success",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
                "temp_audio_location": new_blob_name,
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