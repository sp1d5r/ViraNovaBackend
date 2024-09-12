from pytubefix import YouTube
import pandas as pd
from pytubefix.innertube import _default_clients
import random
from serverless_backend.services.firebase import FirebaseService
import subprocess
import os
from moviepy.editor import VideoFileClip, AudioFileClip


def add_audio_to_video(video_path, audio_path):
    output_path = video_path.rsplit('.', 1)[0] + '_with_audio.mp4'

    command = [
        'ffmpeg',
        '-i', video_path,
        '-i', audio_path,
        '-c', 'copy',  # Copy the video codec without re-encoding
        output_path
    ]

    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        print("FFmpeg output:")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print("FFmpeg error output:")
        print(e.stderr)
        raise

    # Verify the output file
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        print(f"Output file created successfully. Size: {os.path.getsize(output_path)} bytes")
    else:
        raise Exception("Failed to create output video file with audio")

    return output_path


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

        # current files location using os
        cwd = os.getcwd()
        token_file = cwd + "/tokenoauth.json"

        print('Token File: ', token_file)
        print('Token File exists: ', os.path.isfile(token_file))
        yt = YouTube(url, proxies=proxies, use_oauth=True, allow_oauth_cache=True, token_file=token_file)
        update_progress(20)
        update_progress_message("Beginning Download - Highest resolution, you're welcome")

        video_stream = yt.streams.filter(adaptive=True, file_extension='mp4', only_video=True).order_by(
            'resolution').desc().first()
        audio_stream = yt.streams.filter(adaptive=True, file_extension='mp4', only_audio=True).order_by(
            'abr').desc().first()

        print(video_stream)
        video_path = video_stream.download(filename_prefix="video", output_path='/tmp')
        print(video_path)
        audio_path = audio_stream.download(filename_prefix="audio", output_path='/tmp')

        output_path = add_audio_to_video(video_path, audio_path)

        update_progress(40)
        update_progress_message("Downloading Audio")

        update_progress(70)
        update_progress_message("Downloading transcripts")
        print(yt.captions)
        transcript = download_transcript_from_video_id(yt.captions, video_id)

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
    return output_path, audio_path, transcript


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


def download_transcript_from_video_id(captions, video_id):
    try:
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

