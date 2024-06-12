import ast
from io import BytesIO
import random
from flask import Blueprint, jsonify
from services.firebase import FirebaseService
from services.handle_operations_from_logs import handle_operations_from_logs
from pydub import AudioSegment
from datetime import datetime

from services.verify_video_document import parse_and_verify_short, parse_and_verify_video, parse_and_verify_segment

generate_test_audio = Blueprint("generate_test_audio", __name__)


@generate_test_audio.route("/generate-test-audio/<short_id>")
def generate_test_audio_for_short(short_id):
    try:
        firebase_service = FirebaseService()
        short_document = firebase_service.get_document("shorts", short_id)
        update_progress = lambda x: firebase_service.update_document("shorts", short_id, {"update_progress": x})
        update_message = lambda x: firebase_service.update_document("shorts", short_id, {"progress_message": x, "last_updated": datetime.now()})

        is_valid_document, error_message = parse_and_verify_short(short_document)
        if is_valid_document:
            firebase_service.update_document('shorts', short_id, {'temp_audio_file': "Loading..."})
            firebase_service.update_document("shorts", short_id, {"pending_operation": True})

            update_message("Collected Short Document")
            logs = short_document['logs']
            update_progress(20)

            if "video_id" in short_document.keys():
                video_id = short_document['video_id']
            else:
                firebase_service.update_document("shorts", short_id, {"pending_operation": False})
                return jsonify(
                    {
                        "status": "error",
                        "data": {
                            "short_id": short_id,
                            "error": "No video id in short..."
                        },
                        "message": "Failed to generate audio for clip"
                    }), 404

            video_document = firebase_service.get_document('videos', video_id)
            is_valid_document, error_message = parse_and_verify_video(video_document)

            update_progress(40)
            if not is_valid_document:
                update_message("Not related to an original video... Contact someone...")
                firebase_service.update_document("shorts", short_id, {"pending_operation": False})
                return jsonify(
                    {
                        "status": "error",
                        "data": {
                            "short_id": short_id,
                            "error": error_message
                        },
                        "message": "Failed to generate audio for clip"
                    }), 400
            else:
                update_message("Collected video document")

            audio_file = video_document['audio_path']

            segment_document = firebase_service.get_document('topical_segments', short_document['segment_id'])
            is_valid_document, error_message = parse_and_verify_segment(segment_document)

            if not is_valid_document:
                update_message("Not related to an segment... Contact someone...")
                firebase_service.update_document("shorts", short_id, {"pending_operation": False})
                return jsonify(
                    {
                        "status": "error",
                        "data": {
                            "short_id": short_id,
                            "error": error_message
                        },
                        "message": "Failed to generate audio for clip"
                    }), 400
            else:
                update_message("Collected segmnet document")

            segment_document_words = ast.literal_eval(segment_document['words'])
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
            total_length = 0  # To keep track of expected length
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

            update_message(str("Final combined length (from segments):" + str(total_length)))
            update_message(str("Actual combined audio length:" + str(len(combined_audio))))

            update_message("Loading the bytes stream")
            byte_stream = BytesIO()
            combined_audio.export(byte_stream,
                                 format='mp4')  # Use 'mp4' as the format; adjust as necessary for your audio type

            update_message(("New combined audio length:", str(len(combined_audio))))

            new_blob_location = 'temp-audio/' + "".join(audio_file.split("/")[1:])

            byte_stream.seek(0)
            file_bytes = byte_stream.read()
            firebase_service.upload_audio_file_from_memory(new_blob_location, file_bytes)

            update_message("Uploaded Result")
            update_progress(100)
            firebase_service.update_document('shorts', short_id, {'temp_audio_file': new_blob_location})
            firebase_service.update_document("shorts", short_id, {"pending_operation": False})
            return jsonify(
                    {
                        "status": "success",
                        "data": {
                            "short_id": short_id,
                            "temp_audio_location": new_blob_location,
                        },
                        "message": "Successfully generated audio for clip"
                    }), 200
        else:
            return jsonify(
                    {
                        "status": "error",
                        "data": {
                            "short_id": short_id,
                            "error": error_message
                        },
                        "message": "Failed to generate audio for clip"
                    }), 400
    except Exception as e:
        return jsonify(
            {
                "status": "error",
                "data": {
                    "short_id": short_id,
                    "error": e
                },
                "message": "Failed to generate audio for clip"
            }), 400
