from serverless_backend.services.verify_video_document import parse_and_verify_video
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.google_text_to_speech import GoogleSpeechService
from flask import Blueprint, jsonify

transcribe_and_diarize_audio = Blueprint("transcribe_and_diarize_audio", __name__)

@transcribe_and_diarize_audio.route("/v1/transcribe-and-diarize/<video_id>", methods=['GET'])
def transcribe_and_diarize(video_id: str):
    try:
        # Access video document and verify existance
        firebase_service = FirebaseService()
        tts_service = GoogleSpeechService()
        video_document = firebase_service.get_document("videos", video_id)
        is_valid_document, error_message = parse_and_verify_video(video_document)
        update_progress_message = lambda x: firebase_service.update_document('videos', video_id,
                                             {'progressMessage': x})
        update_progress = lambda x: firebase_service.update_document('videos', video_id,
                                                                             {'processingProgress': x})
        if is_valid_document and "audio_path" in video_document:
            audio_path = video_document['audio_path']

            update_progress(0)
            update_progress_message("Beginning Transcribing.")

            diarized = False
            transcribed_content = tts_service.transcribe_gcs(
                audio_path,
                update_progress,
                update_progress_message,
                enable_diarization=diarized,
                diarization_speaker_count=5
            )

            # Convert the RecognizeResponse to a dictionary or string
            print(transcribed_content, type(transcribed_content))

            update_progress_message("Uploading transcript to database...")
            transcript_data, word_data = firebase_service.upload_transcription_to_firestore(transcribed_content, video_id, update_progress)
            update_progress_message("Transcription and Diarization Complete...")

            # Return the response as JSON
            firebase_service.update_document('videos', video_id, {'status': "Segmenting"})
            return jsonify(
                {
                    "status": "success",
                    "data": {
                        "video_id": video_id,
                        "transcript_data": transcript_data,
                        "word_data": word_data
                    },
                    "message": "Successfully transcribed and diarized audio"
                }), 200

        else:
            return jsonify(
                {
                    "status": "error",
                    "data": {
                        "video_id": video_id,
                        "error": error_message
                    },
                    "message": "Failed to transcribe and diarize audio"
                }), 400
    except Exception as e:
        return jsonify(
            {
                "status": "error",
                "data": {
                    "video_id": video_id,
                    "error": str(e)
                },
                "message": "Failed to transcribe and diarize audio"
            }), 400
