from flask import Blueprint
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.youtube.youtube_api import YouTubeAPIService

add_channel = Blueprint("add_channel", __name__)


@add_channel.route("/v1/get-channel-information/<channel_id>", methods=['GET'])
def get_channel_information(channel_id):
    youtube_service = YouTubeAPIService()
    firebase_service = FirebaseService()

    try:
        channel_info = youtube_service.get_channel_info(channel_id)

        if channel_info:
            firebase_service.update_document(
                'channels',
                channel_id,
                channel_info
            )
        else:
            firebase_service.update_document(
                'channels',
                channel_id,
                {
                    'description': 'No Channel with that ID Found...',
                    'status': 'Error'
                }
            )
    except Exception as e:
        firebase_service.update_document(
            'channels',
            channel_id,
            {
                'description': str(e),
                'status': 'Error'
            }
        )