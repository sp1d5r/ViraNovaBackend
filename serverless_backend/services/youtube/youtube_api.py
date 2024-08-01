from datetime import datetime
import os
from googleapiclient.discovery import build
from isodate import parse_duration

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

    def get_video_info(self, video_id):
        try:
            response = self.youtube.videos().list(
                part='snippet,contentDetails,statistics,topicDetails,status',
                id=video_id
            ).execute()

            if 'items' in response and len(response['items']) > 0:
                video_data = response['items'][0]
                snippet = video_data['snippet']
                content_details = video_data['contentDetails']
                statistics = video_data['statistics']
                status = video_data['status']

                # Parse duration
                duration = parse_duration(content_details['duration'])
                duration_str = str(duration)

                # Construct video URL
                video_url = f"https://www.youtube.com/watch?v={video_id}"

                # Construct thumbnails
                thumbnails = {
                    size: {
                        'url': thumb['url'],
                        'width': thumb.get('width', 0),
                        'height': thumb.get('height', 0)
                    } for size, thumb in snippet['thumbnails'].items()
                }

                return {
                    'videoId': video_id,
                    'videoTitle': snippet['title'],
                    'videoDescription': snippet['description'],
                    'videoUrl': video_url,
                    'thumbnailUrl': snippet['thumbnails']['default']['url'],
                    'channelId': snippet['channelId'],
                    'channelTitle': snippet['channelTitle'],
                    'publishedAt': snippet['publishedAt'],
                    'duration': duration_str,
                    'viewCount': int(statistics.get('viewCount', 0)),
                    'likeCount': int(statistics.get('likeCount', 0)),
                    'commentCount': int(statistics.get('commentCount', 0)),
                    'tags': snippet.get('tags', []),
                    'categoryId': snippet['categoryId'],
                    'defaultLanguage': snippet.get('defaultLanguage'),
                    'defaultAudioLanguage': snippet.get('defaultAudioLanguage'),
                    'isLiveBroadcast': content_details.get('livestream', False),
                    'liveBroadcastContent': snippet['liveBroadcastContent'],
                    'dimension': content_details['dimension'],
                    'definition': content_details['definition'],
                    'caption': 'caption' in content_details,
                    'licensedContent': content_details.get('licensedContent', False),
                    'projection': content_details['projection'],
                    'topicCategories': video_data.get('topicDetails', {}).get('topicCategories', []),
                    'statistics': {
                        'viewCount': int(statistics.get('viewCount', 0)),
                        'likeCount': int(statistics.get('likeCount', 0)),
                        'dislikeCount': int(statistics.get('dislikeCount', 0)),
                        'favoriteCount': int(statistics.get('favoriteCount', 0)),
                        'commentCount': int(statistics.get('commentCount', 0)),
                    },
                    'thumbnails': thumbnails,
                }
            else:
                return None
        except Exception as e:
            print(f"Error fetching video info: {str(e)}")
            raise e


if __name__=="__main__":
    yt = YouTubeAPIService()
    print(yt.get_video_info('wDlePmoAAso'))