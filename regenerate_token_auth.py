import os
import random
from pytubefix import YouTube
from pytubefix.innertube import _default_clients
from serverless_backend.services.firebase import FirebaseService

"""

How to regenerate the youtube token. 
- 1) Delete teh tokenoauth.json file (or if it doesn't exist just forget it)
- 2) run this script 
- 3) When you get the device stuff follow it. The oauth token dies after 24hrs 

last updated: 15:17, Mon 19th Aug

"""

def get_random_proxy():
    firebase_service = FirebaseService()
    proxies = firebase_service.get_all_documents('proxies')
    proxies = [i for i in proxies if i['status'] == 'UP']
    return random.choice(proxies) if proxies else None

def download_random_video():
    # List of popular video IDs (you can expand or modify this list)
    video_ids = [
        "dQw4w9WgXcQ",  # Never Gonna Give You Up
        "9bZkp7q19f0",  # Gangnam Style
        "JGwWNGJdvx8",  # Shape of You
        "kJQP7kiw5Fk",  # Despacito
        "OPf0YbXqDm0",  # Uptown Funk
    ]

    # Select a random video ID
    random_video_id = random.choice(video_ids)
    url = f"https://www.youtube.com/watch?v={random_video_id}"

    try:
        # Get a random proxy
        proxy = get_random_proxy()
        if proxy:
            ip = proxy['ip']
            port = proxy['port']
            username = proxy['username']
            password = proxy['password']
            proxies = {"http": f"https://{username}:{password}@{ip}:{port}"}
            print(f"Using proxy: {ip}:{port}")
        else:
            proxies = None
            print("No proxy available, proceeding without proxy")

        # Set the ANDROID_MUSIC client to use the WEB client
        _default_clients["ANDROID_MUSIC"] = _default_clients["WEB"]

        # Get the current working directory
        cwd = os.getcwd()
        token_file = os.path.join(cwd, "tokenoauth.json")

        print(f'Token File: {token_file}')
        print(f'Token File exists: {os.path.isfile(token_file)}')

        # Create YouTube object with OAuth and proxy
        yt = YouTube(url, use_oauth=True, allow_oauth_cache=True, token_file=token_file, proxies=proxies)

        print(f"Downloading: {yt.title}")

        # Get the highest resolution stream
        video = yt.streams.get_highest_resolution()

        # Download the video
        output_path = os.path.join(cwd, "downloads")
        os.makedirs(output_path, exist_ok=True)
        video_path = video.download(output_path=output_path)

        print(f"Download complete! File saved to: {video_path}")

    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    download_random_video()