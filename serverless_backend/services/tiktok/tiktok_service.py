import os
import requests

class TikTokService:
    def __init__(self):
        self.api_key = os.getenv('TIKTOK_API_KEY')
        self.base_url = 'https://open.tiktokapis.com'

    def query_creator_info(self, user_access_token):
        try:
            url = f"{self.base_url}/v2/post/publish/creator_info/query/"
            headers = {
                'Authorization': f"Bearer {user_access_token}",
                'Content-Type': 'application/json; charset=UTF-8'
            }
            response = requests.post(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error querying creator info: {str(e)}")
            raise e

if __name__ == "__main__":
    tiktok_service = TikTokService()
    user_access_token = 'example_user_access_token'
    print(tiktok_service.query_creator_info(user_access_token))