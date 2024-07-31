from datetime import datetime
import os
from googleapiclient.discovery import build

class YouTubeAPIService:
    def __init__(self):
        api_key = os.getenv('YOUTUBE_API_KEY')
        self.youtube = build('youtube', 'v3', developerKey=api_key)

    def get_channel_info(self, channel_id):
        try:
            response = self.youtube.channels().list(
                part='snippet,statistics,contentDetails,brandingSettings,topicDetails,status',
                id=channel_id
            ).execute()

            if 'items' in response and len(response['items']) > 0:
                channel_data = response['items'][0]
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Extract all available thumbnail URLs
                thumbnails = {size: data['url'] for size, data in channel_data['snippet']['thumbnails'].items()}

                return {
                    'channelId': channel_id,
                    'title': channel_data['snippet']['title'],
                    'description': channel_data['snippet']['description'],
                    'customUrl': channel_data['snippet'].get('customUrl'),
                    'publishedAt': channel_data['snippet']['publishedAt'],
                    'thumbnails': thumbnails,
                    'country': channel_data['snippet'].get('country'),
                    'defaultLanguage': channel_data['snippet'].get('defaultLanguage'),

                    # Statistics
                    'viewCount': channel_data['statistics']['viewCount'],
                    'subscriberCount': channel_data['statistics']['subscriberCount'],
                    'hiddenSubscriberCount': channel_data['statistics']['hiddenSubscriberCount'],
                    'videoCount': channel_data['statistics']['videoCount'],

                    # Content Details
                    'relatedPlaylists': channel_data['contentDetails']['relatedPlaylists'],

                    # Branding Settings
                    'channel': channel_data['brandingSettings'].get('channel', {}),
                    'image': channel_data['brandingSettings'].get('image', {}),

                    # Topic Details
                    'topicCategories': channel_data.get('topicDetails', {}).get('topicCategories', []),

                    # Status
                    'privacyStatus': channel_data['status']['privacyStatus'],
                    'isLinked': channel_data['status']['isLinked'],
                    'longUploadsStatus': channel_data['status']['longUploadsStatus'],
                    'madeForKids': channel_data['status'].get('madeForKids'),
                    'selfDeclaredMadeForKids': channel_data['status'].get('selfDeclaredMadeForKids'),
                    'status': f"Last Collected on {current_time}",
                }
            else:
                return None
        except Exception as e:
            print(f"Error fetching channel info: {str(e)}")
            raise e

