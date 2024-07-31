from flask import Blueprint, request, abort
import xml.etree.ElementTree as ET
import requests

youtube_webhook = Blueprint("youtube_webhook", __name__)


@youtube_webhook.route('/youtube-webhook', methods=['GET', 'POST'])
def handle_youtube_webhook():
    if request.method == 'GET':
        # Handle the subscription verification
        mode = request.args.get('hub.mode')
        challenge = request.args.get('hub.challenge')
        if mode == 'subscribe' and challenge:
            return challenge
        else:
            abort(400)
    elif request.method == 'POST':
        # Handle the actual notification
        if request.headers.get('content-type') == 'application/atom+xml':
            root = ET.fromstring(request.data)
            video_id = root.find('.//{http://www.youtube.com/xml/schemas/2015}videoId').text
            channel_id = root.find('.//{http://www.youtube.com/xml/schemas/2015}channelId').text
            print(f"New video {video_id} posted by channel {channel_id}")
            # Here you would typically update your database or trigger other actions
            return '', 204
        else:
            abort(400)