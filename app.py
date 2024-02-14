from flask import Flask, jsonify
from services.firebase import FirebaseService
from services.google_text_to_speech import GoogleSpeechService
from routes.split_video_and_audio import extract_audio_from_video
from routes.verify_video_document import parse_and_verify_video

app = Flask(__name__)


@app.route('/split-video/<video_id>')
def split_video_to_audio_and_video(video_id: str):

    # Access video document and verify existance
    firebase_service = FirebaseService()
    video_document = firebase_service.get_document("videos", video_id)
    is_valid_document, error_message = parse_and_verify_video(video_document)

    if is_valid_document:
        firebase_service.update_document('videos', video_id, {'status': "Transcribing"})
        firebase_service.update_document('videos', video_id, {'progressMessage': "Splitting audio from video."})
        print("Updated document ")
        file_storage_path = video_document['videoPath']

        # Download the video
        video_downloaded = firebase_service.download_file_to_memory(file_storage_path)
        audio_bytes = extract_audio_from_video(video_downloaded)
        firebase_service.update_document('videos', video_id, {'progressMessage': "Audio split - uploading to firebase."})
        audio_blob_name = "audio/" + video_document['originalFileName'].replace('.mp4', '_audio.mp4')
        firebase_service.upload_audio_file_from_memory(audio_blob_name, audio_bytes)
        firebase_service.update_document('videos', video_id, {
            'processingProgress': 50,
            'audio_path': audio_blob_name
        })

        firebase_service.update_document('videos', video_id,
                                         {'progressMessage': "Audio file uploaded."})

        return "Converted Video", 200
    else:
        return error_message, 404


@app.route("/transcribe-and-diarize/<video_id>")
def transcribe_and_diarize(video_id: str):
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

        diarized = True
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
        firebase_service.upload_transcription_to_firestore(transcribed_content, video_id, update_progress)
        transcript_data, word_data = update_progress_message("Transcription and Diarization Complete...")

        # Return the response as JSON
        return jsonify({"transcript_data": transcript_data, "word_data": word_data}), 200

    else:
        return error_message, 404


if __name__ == '__main__':
    app.run(debug=True)
