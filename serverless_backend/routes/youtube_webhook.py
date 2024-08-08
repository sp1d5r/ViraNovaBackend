from datetime import datetime, timedelta
from flask import Blueprint, request, abort
import xml.etree.ElementTree as ET
from serverless_backend.services.youtube.youtube_api import YouTubeAPIService
from serverless_backend.services.firebase import FirebaseService


youtube_webhook = Blueprint("youtube_webhook", __name__)


def parse_duration(duration_str):
    # Split the duration string into parts
    parts = duration_str.split(':')

    if len(parts) == 3:
        # Format is 'hours:minutes:seconds'
        hours, minutes, seconds = map(int, parts)
    elif len(parts) == 2:
        # Format is 'minutes:seconds'
        hours = 0
        minutes, seconds = map(int, parts)
    elif len(parts) == 1:
        # Format is 'seconds'
        hours = 0
        minutes = 0
        seconds = int(parts[0])
    else:
        raise ValueError(f"Unexpected duration format: {duration_str}")

    return timedelta(hours=hours, minutes=minutes, seconds=seconds)

@youtube_webhook.route('/youtube-webhook', methods=['GET', 'POST'])
def handle_youtube_webhook():
    firebase_service = FirebaseService()
    if request.method == 'GET':
        # Handle the subscription verification
        mode = request.args.get('hub.mode')
        challenge = request.args.get('hub.challenge')
        if mode == 'subscribe' and challenge:
            print("Found challenge, ", challenge)

            current_time = datetime.utcnow()  # Get current UTC time
            scheduled_time = current_time + timedelta(days=5)
            download_task = {
                'status': 'Pending',
                'scheduledTime': scheduled_time,
                'operation': 'Re-Subscribe',
                'channelId': request.args.get('hub.topic', '').split('=')[-1]
            }

            task_id = firebase_service.add_document(
                "tasks",
                download_task,
            )

            print(f"Resubscribe task {task_id} created for 4 days from now")

            return challenge, 200
        else:
            abort(400)
    elif request.method == 'POST':
        # Handle the actual notification
        print('request headers', request.headers.get('content-type'))
        print('request data', request.data)
        if request.headers.get('content-type') == 'application/atom+xml':
            root = ET.fromstring(request.data)
            published = root.find('.//{http://www.w3.org/2005/Atom}published')
            if published is None:
                print("Not a new video notification. Ignoring.")
                return '', 204

            video_id = root.find('.//{http://www.youtube.com/xml/schemas/2015}videoId').text
            channel_id = root.find('.//{http://www.youtube.com/xml/schemas/2015}channelId').text

            print(f"New video {video_id} posted by channel {channel_id}")

            # Get Video from API
            youtube_service = YouTubeAPIService()
            try:
                video = youtube_service.get_video_info(video_id)

                # Check video length if it's less than 1 minute ignore
                duration = parse_duration(video['duration'])
                if duration < timedelta(minutes=1):
                    print(f"Video {video_id} is shorter than 1 minute. Ignoring.")
                    return '', 204

                video_exists = firebase_service.query_documents("videos", "videoId", video_id)

                if len(video_exists) == 0:
                    # Add it to the videos documents with status "Loading"
                    video['status'] = "Loading..."
                    video_document_id = firebase_service.add_document(
                        "videos",
                        video,
                    )
                else:
                    video_document_id = video_exists[0]['id']

                # Create a new worker task to download the video in 15 minutes from now
                current_time = datetime.utcnow()  # Get current UTC time
                scheduled_time = current_time + timedelta(minutes=15)
                download_task = {
                    'status': 'Pending',
                    'scheduledTime': scheduled_time,
                    'operation': 'Download',
                    'videoId': video_id,
                    'channelId': channel_id,
                    'videoDocumentId': video_document_id
                }

                task_id = firebase_service.add_document(
                    "tasks",
                    download_task,
                )

                print(f"Download task {task_id} created for video {video_id}")

                return '', 204
            except Exception as e:
                print(f"Error processing video {video_id}: {str(e)}")
                abort(500)
        else:
            abort(400)