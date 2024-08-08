from flask import Blueprint, jsonify
from serverless_backend.services.verify_video_document import parse_and_verify_video
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.transcription.deep_gram_transcriber import DeepgramTranscriberService

transcribe = Blueprint("transcribe", __name__)


@transcribe.route("/v1/transcribe/<video_id>", methods=['GET'])
def transcribe_video(video_id):
    try:
        # Access video document and verify existence
        firebase_service = FirebaseService()
        deepgram_service = DeepgramTranscriberService()

        video_document = firebase_service.get_document("videos", video_id)
        is_valid_document, error_message = parse_and_verify_video(video_document)

        update_progress_message = lambda x: firebase_service.update_document('videos', video_id, {'progressMessage': x})
        update_progress = lambda x: firebase_service.update_document('videos', video_id, {'processingProgress': x})

        if is_valid_document and "audio_path" in video_document:
            audio_path = video_document['audio_path']
            firebase_url = firebase_service.get_signed_url(audio_path)
            update_progress(0)
            update_progress_message("Beginning Transcribing.")

            transcribed_content = deepgram_service.transcribe(
                firebase_url,
                update_progress,
                update_progress_message
            )

            update_progress_message("Uploading transcript to database...")
            transcript_data = firebase_service.upload_deepgram_transcription_to_firestore(transcribed_content, video_id,
                                                                                          update_progress)
            update_progress_message("Transcription Complete...")

            # Return the response as JSON
            firebase_service.update_document('videos', video_id, {'status': "Segmenting"})
            return jsonify(
                {
                    "status": "success",
                    "data": {
                        "video_id": video_id,
                        "transcript_data": transcript_data,
                    },
                    "message": "Successfully transcribed audio"
                }), 200

        else:
            return jsonify(
                {
                    "status": "error",
                    "data": {
                        "video_id": video_id,
                        "error": error_message
                    },
                    "message": "Failed to transcribe audio"
                }), 400
    except Exception as e:
        return jsonify(
            {
                "status": "error",
                "data": {
                    "video_id": video_id,
                    "error": str(e)
                },
                "message": "Failed to transcribe audio"
            }), 400