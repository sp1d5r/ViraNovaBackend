import subprocess
from tempfile import NamedTemporaryFile
import os
from flask import Blueprint, jsonify
from serverless_backend.services.verify_video_document import parse_and_verify_video
from serverless_backend.services.firebase import FirebaseService


def extract_audio_from_video(video_bytes):
    # Create a temporary file for the video
    with NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_video:
        tmp_video_name = tmp_video.name
        tmp_video.write(video_bytes.getbuffer())

    # Define the temporary audio file name
    tmp_audio_name = tmp_video_name.replace('.mp4', '_audio.wav')

    # Use FFmpeg to extract audio
    subprocess.run([
        'ffmpeg',
        '-i', tmp_video_name,  # Input video file
        '-vn',
        '-acodec', 'pcm_s16le',  # Use Linear PCM format
        '-ar', '16000',  # Set sample rate to 16000 Hz
        '-ac', '1',  # Set audio channels to mono
        tmp_audio_name  # Output audio file name
    ], check=True)

    # Read the audio file back into memory
    with open(tmp_audio_name, 'rb') as audio_file:
        audio_bytes = audio_file.read()

    # Cleanup temporary files
    os.remove(tmp_video_name)
    os.remove(tmp_audio_name)

    return audio_bytes


split_video_and_audio = Blueprint('split_video_and_audio', __name__)

@split_video_and_audio.route('/v1/split-video/<video_id>', methods=['GET'])
def split_video_to_audio_and_video(video_id: str):
    firebase_service = FirebaseService()
    video_document = firebase_service.get_document("videos", video_id)
    is_valid_document, error_message = parse_and_verify_video(video_document)

    if is_valid_document:
        firebase_service.update_document('videos', video_id, {'progressMessage': "Splitting audio from video."})
        print("Updated document ")
        file_storage_path = video_document['videoPath']

        # Download the video
        video_downloaded = firebase_service.download_file_to_memory(file_storage_path)
        audio_bytes = extract_audio_from_video(video_downloaded)
        firebase_service.update_document('videos', video_id,
                                         {'progressMessage': "Audio split - uploading to firebase."})
        audio_blob_name = "audio/" + video_document['originalFileName'].replace('.mp4', '_audio.wav')
        firebase_service.upload_audio_file_from_memory(audio_blob_name, audio_bytes)
        firebase_service.update_document('videos', video_id, {
            'processingProgress': 50,
            'audio_path': audio_blob_name
        })

        firebase_service.update_document('videos', video_id,
                                         {'progressMessage': "Audio file uploaded."})

        firebase_service.update_document('videos', video_id, {'status': "Transcribing"})
        return jsonify(
            {
                "status": "success",
                "data": {
                    "video_id": video_id,
                },
                "message": "Successfully split audio from video"
            }), 200
    else:
        return jsonify(
            {
                "status": "error",
                "data": {
                    "video_id": video_id,
                    "error": error_message
                },
                "message": "Failed to split audio from video"
            }), 400
