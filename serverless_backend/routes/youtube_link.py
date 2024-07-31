from flask import Blueprint, jsonify
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.verify_video_document import parse_and_verify_video
from serverless_backend.services.youtube.youtube_downloader import download_video

youtube_link = Blueprint("youtube_link", __name__)


@youtube_link.route("/v1/begin-youtube-link-download/<video_id>", methods=['GET'])
def begin_youtube_link_download(video_id: str):
    try:
        firebase_service = FirebaseService()
        video_document = firebase_service.get_document("videos", video_id)
        is_valid_document, error_message = parse_and_verify_video(video_document)

        update_progress_message = lambda x: firebase_service.update_document('videos', video_id,
                                                                             {'progressMessage': x})
        update_progress = lambda x: firebase_service.update_document('videos', video_id,
                                                                     {'processingProgress': x})

        if is_valid_document:
            try:
                firebase_service.update_document('videos', video_id, {'progressMessage': "Downloading Youtube Video"})

                video_link = video_document['link']

                # Download video information
                temp_video_path, temp_audio_path, transcript = download_video(video_id, video_link, update_progress, update_progress_message)

                print("Video Path", temp_video_path)
                print("Audio Path", temp_audio_path)
                print("Transcript", transcript)

                video_filename = temp_video_path.split('/')[-1]
                audio_filename = temp_audio_path.split('/')[-1]

                firebase_service.update_document('videos', video_id, {
                    "originalFileName": video_filename
                })

                video_blob_destination = f"videos-raw/{video_id}/{video_filename}"
                firebase_service.upload_file_from_temp(temp_video_path, video_blob_destination)

                audio_blob_destination = f"audio/{video_id}/{audio_filename}"
                firebase_service.upload_file_from_temp(temp_audio_path, audio_blob_destination)

                # Upload transcript and update document with path references
                update_progress_message("Uploading to transcript")
                update_progress(80)
                transcript_data, word_data = firebase_service.upload_youtube_transcription_to_firestore(transcript, video_id, update_progress)

                print("Transcript Data: ", transcript_data)
                print("Word Data: ", word_data)

                firebase_service.update_document('videos', video_id, {
                    "videoPath": video_blob_destination,
                    "audio_path": audio_blob_destination
                })

                firebase_service.update_document('videos', video_id,
                                                 {'progressMessage': "Video data downloaded"})
                update_progress_message("Video transcript uploaded!")
                update_progress(100)
                firebase_service.update_document('videos', video_id, {'status': "Segmenting"})
                return jsonify(
                    {
                        "status": "success",
                        "data": {
                            "video_id": video_id,
                        },
                        "message": "Successfully downloaded youtube video"
                    }), 200
            except Exception as e:
                update_progress_message("Try a different video -" +  str(e))
                print(e)
                update_progress(0)
                return jsonify(
                    {
                        "status": "error",
                        "data": {
                            "video_id": video_id,
                            "error": str(e)
                        },
                        "message": "Failed to download youtube video"
                    }), 400
        else:
            return jsonify(
                {
                    "status": "error",
                    "data": {
                        "video_id": video_id,
                        "error": error_message
                    },
                    "message": "Failed to download youtube video"
                }), 400
    except Exception as e:
        return jsonify(
            {
                "status": "error",
                "data": {
                    "video_id": video_id,
                    "error": str(e)
                },
                "message": "Failed to download youtube video"
            }), 400