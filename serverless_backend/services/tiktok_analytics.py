import os

import requests
import time


class TikTokAnalytics():
    def __init__(self):
        self.API_TOKEN = os.getenv("APIFY_TOKEN")
        self.BASE_URL = 'https://api.apify.com/v2'


    def get_tiktok_video_details(self, post_url):
        # Set headers for authentication
        headers = {
            'Authorization': f'Bearer {self.API_TOKEN}',
            'Content-Type': 'application/json'
        }
        # Define the endpoint for starting the actor
        actor_id = 'clockworks~free-tiktok-scraper'
        start_endpoint = f'{self.BASE_URL}/acts/{actor_id}/runs'
        # Define the payload with the input for the actor
        payload = {
            "postURLs": [post_url],
            "shouldDownloadCovers": False,
            "shouldDownloadSlideshowImages": False,
            "shouldDownloadSubtitles": False,
            "shouldDownloadVideos": False
        }
        # Make the POST request to start the actor
        response = requests.post(start_endpoint, json=payload, headers=headers)
        if response.status_code != 201:
            print(f'Error: {response.status_code} - {response.text}')
            return None
        # Get the run ID and default dataset ID from the response
        run_data = response.json()
        run_id = run_data['data']['id']
        default_dataset_id = run_data['data']['defaultDatasetId']
        # Define the endpoint for getting the status of the run
        status_endpoint = f'{self.BASE_URL}/acts/{actor_id}/runs/{run_id}'
        # Poll the status of the run until it is finished
        while True:
            response = requests.get(status_endpoint, headers=headers)
            if response.status_code != 200:
                print(f'Error: {response.status_code} - {response.text}')
                return None
            run_status = response.json()['data']['status']
            if run_status == 'SUCCEEDED':
                break
            elif run_status in ['FAILED', 'TIMED-OUT']:
                print(f'Run failed with status: {run_status}')
                return None
            print('Run in progress, waiting...')
            time.sleep(5)  # Wait for 5 seconds before checking again
        # Get the results of the run using the defaultDatasetId
        dataset_items_endpoint = f'{self.BASE_URL}/datasets/{default_dataset_id}/items'
        response = requests.get(dataset_items_endpoint, headers=headers)
        if response.status_code != 200:
            print(f'Error: {response.status_code} - {response.text}')
            return None
        # Return the JSON response containing the video details
        return response.json()

    def get_tiktok_comments(self, post_url, comments_count):
        headers = {
            'Authorization': f'Bearer {self.API_TOKEN}',
            'Content-Type': 'application/json'
        }
        actor_id = 'clockworks~tiktok-comments-scraper'
        start_endpoint = f'{self.BASE_URL}/acts/{actor_id}/runs'

        payload = {
            "commentsPerPost": min(comments_count, 50),
            "maxRepliesPerComment": 0,
            "postURLs": [post_url]
        }

        response = requests.post(start_endpoint, json=payload, headers=headers)
        if response.status_code != 201:
            print(f'Error: {response.status_code} - {response.text}')
            return None

        run_data = response.json()
        run_id = run_data['data']['id']
        default_dataset_id = run_data['data']['defaultDatasetId']

        status_endpoint = f'{self.BASE_URL}/acts/{actor_id}/runs/{run_id}'

        while True:
            response = requests.get(status_endpoint, headers=headers)
            if response.status_code != 200:
                print(f'Error: {response.status_code} - {response.text}')
                return None
            run_status = response.json()['data']['status']
            if run_status == 'SUCCEEDED':
                break
            elif run_status in ['FAILED', 'TIMED-OUT']:
                print(f'Run failed with status: {run_status}')
                return None
            print('Run in progress, waiting...')
            time.sleep(5)

        dataset_items_endpoint = f'{self.BASE_URL}/datasets/{default_dataset_id}/items'
        response = requests.get(dataset_items_endpoint, headers=headers)
        if response.status_code != 200:
            print(f'Error: {response.status_code} - {response.text}')
            return None

        return response.json()
