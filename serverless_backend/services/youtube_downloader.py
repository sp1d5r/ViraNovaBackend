from pytubefix import YouTube
import pandas as pd
import subprocess
from pytubefix.innertube import _default_clients
import random
from serverless_backend.services.firebase import FirebaseService


def download_video(video_id, url, update_progress, update_progress_message):
    firebase_service = FirebaseService()
    proxies = firebase_service.get_all_documents('proxies')
    proxies = [i for i in proxies if i['status'] == 'UP']

    proxy = random.choice(proxies)

    ip = proxy['ip']
    port = proxy['port']
    username = proxy['username']
    password = proxy['password']

    proxies = {"http": f"https://{username}:{password}@{ip}:{port}"}

    try:
        _default_clients["ANDROID_MUSIC"] = _default_clients["WEB"]
        yt = YouTube(url, proxies=proxies)
        update_progress(20)
        update_progress_message("Beginning Download - Highest resolution, you're welcome")
        video = yt.streams.get_highest_resolution()

        video_path = video.download(output_path="/tmp")  # download video to temp path
        update_progress(40)
        update_progress_message("Downloading Audio")
        audio_path = extract_audio(video_path)

        update_progress(70)
        update_progress_message("Downloading transcripts")
        transcript = download_transcript_from_video_id(video_id, url, proxies)
    except Exception as e:
        firebase_service.add_document(
            'proxy_usage',
            {
                'video_id': video_id,
                'proxy': proxy,
                'status': 'FAILED',
                'video_url': url,
                'error': str(e),
            }
        )
        raise Exception(e)
    return video_path, audio_path, transcript


def extract_audio(video_path):
    audio_path = video_path.replace('.mp4', '.wav')
    # Command to extract audio using ffmpeg, outputting in WAV format
    command = [
        'ffmpeg',
        '-y',
        '-i', video_path,   # Input video file
        '-vn',              # No video output
        '-acodec', 'pcm_s16le',  # Linear PCM format for WAV
        '-ar', '44100',     # Audio sample rate
        '-ac', '2',         # Number of audio channels
        audio_path          # Output audio file
    ]

    # Run the command with subprocess
    subprocess.run(command, check=True)
    return audio_path


def clean_captions(video_id, caption, key):
    events = [i for i in caption['events'] if 'segs' in i and 'dDurationMs' in i and 'tStartMs']
    words = []

    for event_index, event in enumerate(events):
        seg_start_time = int(event['tStartMs'])
        seg_duration = int(event['dDurationMs'])

        for seg_index, seg in enumerate(event['segs']):
            if 'utf8' in seg and seg['utf8'].strip() != '':
                if seg_index < len(event['segs']) - 1:
                    word_info = {
                        'transcript_id': f"{video_id}_{event_index}",  # Unique transcript ID for each segment
                        'start_time': round((seg_start_time + int(seg.get('tOffsetMs', 0))) / 1000, 2),
                        'end_time': round((seg_start_time + int(event['segs'][seg_index + 1].get('tOffsetMs', 0))) / 1000, 2),
                        'word': seg['utf8'].strip(),
                        'confidence': seg.get('acAsrConf', 100) / 100.0,  # Normalizing confidence to 0-1 scale
                        'language': key,
                        'group_index': event_index
                    }
                    words.append(word_info)
                else:
                    word_info = {
                        'transcript_id': f"{video_id}_{event_index}",  # Unique transcript ID for each segment
                        'start_time': round((seg_start_time + int(seg.get('tOffsetMs', 0))) / 1000, 2),
                        'end_time': round((seg_start_time + int(seg_duration)) / 1000, 2),
                        'word': seg['utf8'].strip(),
                        'confidence': seg.get('acAsrConf', 100) / 100.0,  # Normalizing confidence to 0-1 scale
                        'language': key,
                        'group_index': event_index
                    }
                    words.append(word_info)

    # Convert list of words to DataFrame
    cleaned_captions = pd.DataFrame(words)
    return cleaned_captions


def download_transcript_from_video_id(video_id, link, proxies):
    yt = YouTube(link, proxies=proxies)
    try:
        captions = yt.captions
        if not captions:
            print("No Captions Available for Video")
            return None

        if "en" in captions:
            print("Extracting English Captions")
            retrieved_captions = captions.get("en")
            retrieved_captions_json = retrieved_captions.json_captions
            return clean_captions(video_id, retrieved_captions_json, key="en")

        print("Extracting Auto Generated Captions")
        print(captions)
        retrieved_captions = captions.get("a.en")
        retrieved_captions_json = retrieved_captions.json_captions
        return clean_captions(video_id, retrieved_captions_json, key="a.en")
    except Exception as e:
        print(f"Error in Downloading Transcript: {e}")
        return None

