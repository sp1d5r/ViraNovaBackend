from flask import Flask, jsonify
from qdrant_client import QdrantClient, models
from database.production_database import ProductionDatabase
from services.firebase import FirebaseService
from services.google_text_to_speech import GoogleSpeechService
from services.open_ai import OpenAIService
from services.segmentation_loader import load_video_data
from routes.split_video_and_audio import extract_audio_from_video
from routes.verify_video_document import parse_and_verify_video
from routes.determine_topic_boundaries import get_transcript_topic_boundaries, create_segments
import numpy as np
import os
import random
from flask_cors import CORS

TOTAL_AVAILABLE_TOKENS = 8000  # Lower Bound
TOKEN_SIZE = 3
AVERAGE_ENGLISH_WORD_LENGTH = 8
FIXED_SEGMENT_LENGTH = 43
AVERAGE_CHAR_SEGMENT = FIXED_SEGMENT_LENGTH * AVERAGE_ENGLISH_WORD_LENGTH
SEGMENTS_TO_SEND_IN_PARALLEL = int((TOTAL_AVAILABLE_TOKENS * TOKEN_SIZE) / AVERAGE_CHAR_SEGMENT)


app = Flask(__name__)

origins = [
    "http://localhost:3000/segmentation",
    "https://master.d2gor5eji1mb54.amplifyapp.com",
    "http://localhost:5000",
    "http://localhost:8000",
    "http://localhost:3000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:5000"
    "http://127.0.0.1:3000"
]


VIDEO_FOLDER = '/viranova_storage/'

CORS(app, resources={r"/*": {"origins": origins}})

@app.route('/split-video/<video_id>')
def split_video_to_audio_and_video(video_id: str):

    # Access video document and verify existance
    firebase_service = FirebaseService()
    video_document = firebase_service.get_document("videos", video_id)
    is_valid_document, error_message = parse_and_verify_video(video_document)

    if is_valid_document:
        firebase_service.update_document('videos', video_id, {'progressMessage': "Splitting audio from video."})
        print("Updated document ")
        file_storage_path = video_document['videoPath']

        # Download the video
        video_downloaded = firebase_service.download_file_to_memory(file_storage_path)
        audio_bytes = extract_audio_from_video(video_downloaded)
        firebase_service.update_document('videos', video_id, {'progressMessage': "Audio split - uploading to firebase."})
        audio_blob_name = "audio/" + video_document['originalFileName'].replace('.mp4', '_audio.wav')
        firebase_service.upload_audio_file_from_memory(audio_blob_name, audio_bytes)
        firebase_service.update_document('videos', video_id, {
            'processingProgress': 50,
            'audio_path': audio_blob_name
        })

        firebase_service.update_document('videos', video_id,
                                         {'progressMessage': "Audio file uploaded."})

        firebase_service.update_document('videos', video_id, {'status': "Transcribing"})
        return "Converted Video", 200
    else:
        return error_message, 404


@app.route("/transcribe-and-diarize/<video_id>")
def transcribe_and_diarize(video_id: str):
    # Access video document and verify existance
    print("Starting to ")
    firebase_service = FirebaseService()
    tts_service = GoogleSpeechService()
    video_document = firebase_service.get_document("videos", video_id)
    is_valid_document, error_message = parse_and_verify_video(video_document)
    update_progress_message = lambda x: firebase_service.update_document('videos', video_id,
                                         {'progressMessage': x})
    update_progress = lambda x: firebase_service.update_document('videos', video_id,
                                                                         {'processingProgress': x})
    if is_valid_document and "audio_path" in video_document:
        audio_path = video_document['audio_path']

        update_progress(0)
        update_progress_message("Beginning Transcribing.")

        diarized = True
        transcribed_content = tts_service.transcribe_gcs(
            audio_path,
            update_progress,
            update_progress_message,
            enable_diarization=diarized,
            diarization_speaker_count=5
        )

        # Convert the RecognizeResponse to a dictionary or string
        print(transcribed_content, type(transcribed_content))

        update_progress_message("Uploading transcript to database...")
        transcript_data, word_data = firebase_service.upload_transcription_to_firestore(transcribed_content, video_id, update_progress)
        update_progress_message("Transcription and Diarization Complete...")

        # Return the response as JSON
        firebase_service.update_document('videos', video_id, {'status': "Segmenting"})
        return jsonify({"transcript_data": transcript_data, "word_data": word_data}), 200

    else:
        return error_message, 404


def create_fixed_length_transcripts(transcripts_with_words, n=100):
    # List to hold the new fixed-length transcripts
    fixed_length_transcripts = []

    for transcript in transcripts_with_words:
        words = transcript['words']
        # Temporary storage for the current window of words
        window_words = []
        for i in range(len(words)):
            window_words.append(words[i])
            if len(window_words) == n or i == len(words) - 1:
                # Extract start time from the first word in the window
                start_time = window_words[0]['start_time'] if window_words[0]['start_time'] is not None else 0
                # Extract end time from the last word in the window
                end_time = window_words[-1]['end_time']
                # Compile the window words into a transcript text
                transcript_text = " ".join([word['word'] for word in window_words])
                # Append the fixed-length transcript segment to the list
                fixed_length_transcripts.append({
                    'start_time': start_time,
                    'end_time': end_time,
                    'transcript': transcript_text
                })
                # Clear the window for the next segment
                window_words = []

    return fixed_length_transcripts


@app.route("/extract-topical-segments/<video_id>")
def deal_with_topical_segments(video_id: str):
    print("Here")
    firebase_service = FirebaseService()
    open_ai_service = OpenAIService()
    video_document = firebase_service.get_document("videos", video_id)
    is_valid_document, error_message = parse_and_verify_video(video_document)
    update_progress_message = lambda x: firebase_service.update_document('videos', video_id,
                                                                         {'progressMessage': x})
    update_progress = lambda x: firebase_service.update_document('videos', video_id,
                                                                 {'processingProgress': x})

    if is_valid_document:
        transcripts = firebase_service.query_transcripts_by_video_id_with_words(video_id)
        custom_transcript = create_fixed_length_transcripts(transcripts, n=10)
        embeddings = open_ai_service.get_embeddings(custom_transcript, update_progress)
        boundaries = get_transcript_topic_boundaries(embeddings, update_progress, update_progress_message)
        print(boundaries)
        segments = create_segments(custom_transcript, boundaries, video_id, update_progress, update_progress_message)
        update_progress_message("Uploading segments to database")
        for index, segment in enumerate(segments):
            update_progress((index + 1) / len(segments) * 100)
            firebase_service.add_document("topical_segments", segment)

        update_progress_message("Finished Segmenting Video!")
        firebase_service.update_document('videos', video_id, {'status': "Summarizing Segments"})
        return segments, 200
    else:
        return error_message, 404

@app.route("/v0/extract-topical-segments/<video_id>")
def extract_topical_segments(video_id: str):
    # Access video document and verify existance
    firebase_service = FirebaseService()
    open_ai_service = OpenAIService()
    video_document = firebase_service.get_document("videos", video_id)
    is_valid_document, error_message = parse_and_verify_video(video_document)
    update_progress_message = lambda x: firebase_service.update_document('videos', video_id,
                                                                         {'progressMessage': x})
    update_progress = lambda x: firebase_service.update_document('videos', video_id,
                                                                 {'processingProgress': x})

    if is_valid_document:
        update_progress(0)
        update_progress_message("Determining the video topics...")
        transcripts = firebase_service.query_transcripts_by_video_id_with_words(video_id)
        update_progress_message("Extracting Transcript Words")
        words = []

        for transcript_seg in transcripts:
            words.extend(transcript_seg['words'])

        num_transcripts = len(words) // FIXED_SEGMENT_LENGTH + (1 if len(words) % FIXED_SEGMENT_LENGTH != 0 else 0)
        segmented_transcripts = []

        for i in range(num_transcripts):
            start_index = i * FIXED_SEGMENT_LENGTH
            end_index = min((i + 1) * FIXED_SEGMENT_LENGTH, len(words))
            words_segment = words[start_index:end_index]
            segmented_transcripts.append(words_segment)


        fixed_length_segments = [
            {
                'start_time': min([j['start_time'] for j in i if j['start_time'] is not None]),
                'end_time': max([j['end_time'] for j in i if j['end_time'] is not None]),
                'start_index': min([j['index'] for j in i if j['index'] is not None]),
                'end_index': max([j['index'] for j in i if j['index'] is not None]),
                'transcript': ' '.join([j['word'] for j in i if j])
            }
            for i in segmented_transcripts
        ]

        update_progress_message("Getting text embeddings... This might take a while...")

        embeddings = open_ai_service.get_embeddings_parallel([i['transcript'] for i in fixed_length_segments], SEGMENTS_TO_SEND_IN_PARALLEL, update_progress=update_progress)

        update_progress_message("Finding topic changes")
        boundaries = get_transcript_topic_boundaries(embeddings, update_progress, update_progress_message)
        segments = create_segments(fixed_length_segments, boundaries, video_id, update_progress, update_progress_message)

        update_progress_message("Uploading segments to database")
        for index, segment in enumerate(segments):
            update_progress((index+1)/len(segments) * 100)
            firebase_service.add_document("topical_segments", segment)

        update_progress_message("Finished Segmenting Video!")
        firebase_service.update_document('videos', video_id, {'status': "Summarizing Segments"})
        return segments, 200
    else:
        return error_message, 404


@app.route("/summarise-segments/<video_id>")
def summarise_segments(video_id):
    # Access video document and verify existance
    firebase_service = FirebaseService()
    open_ai_service = OpenAIService()
    video_document = firebase_service.get_document("videos", video_id)
    is_valid_document, error_message = parse_and_verify_video(video_document)
    update_progress_message = lambda x: firebase_service.update_document('videos', video_id,
                                                                         {'progressMessage': x})
    update_progress = lambda x: firebase_service.update_document('videos', video_id,
                                                                 {'processingProgress': x})
    print("Here")
    if is_valid_document:
        print("Valid document")
        update_progress(0)
        update_progress_message("Segmenting Topical Segments")
        segments = firebase_service.query_topical_segments_by_video_id(video_id)
        print(segments)
        update_progress_message("Retrieved Segments, Summarising...")
        previous_segment_summary = ""
        for index, segment in enumerate(segments):
            update_progress((index+1) / len(segments) * 100)
            summary = open_ai_service.get_segment_summary(segment['index'], segment['transcript'], previous_segment_summary)
            content_moderation = open_ai_service.extract_moderation_metrics(segment['transcript'])
            segment_summary = summary['segment_summary']
            previous_segment_summary = summary.get("new_combined_summary", previous_segment_summary)
            segment_title = summary.get('segment_title', "Unable to name segment")
            update_progress_message("Description: " + segment_summary[:20] + "...")
            firebase_service.update_document("topical_segments", segment["id"],
                                             {
                                                'segment_summary': segment_summary,
                                                 'segment_title': segment_title,
                                                'flagged': content_moderation['flagged'],
                                                "harassment": content_moderation["harassment"],
                                                "harassment_threatening": content_moderation["harassment_threatening"],
                                                "hate": content_moderation['hate'],
                                                "hate_threatening": content_moderation["hate_threatening"],
                                                "self_harm": content_moderation["self_harm"],
                                                "self_harm_intent": content_moderation['self_harm_intent'],
                                                "sexual": content_moderation['sexual'],
                                                "sexual_minors": content_moderation['sexual_minors'],
                                              })

        update_progress_message("Segments Summarised!")
        firebase_service.update_document("videos", video_id, {'status': 'Preprocessing Complete'})
        return segments, 200
    else:
        return error_message, 404

@app.route("/get-random-video")
def get_random_video():
    try:
        # List all files in the video directory
        files = os.listdir(VIDEO_FOLDER)
        # Filter out files to ensure we only get video files if needed
        video_files = [file for file in files if file.lower().endswith(('.hdf5', '.h5'))]
        if not video_files:
            return "No video files found", 404
        random_video = random.choice(video_files)
        return {"video_file": random_video}
    except Exception as e:
        return str(e), 500


def convert(obj):
    if isinstance(obj, np.generic):
        return obj.item()
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, list):
        return [convert(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: convert(value) for key, value in obj.items()}
    else:
        return obj


@app.route("/load-segmentation-from-file/<video_file>/")
def return_segmentation_masks(video_file: str):
    try:
        video_handler = load_video_data(VIDEO_FOLDER + video_file)
        video_handler = convert(video_handler)
        return jsonify(video_handler)
    except Exception as e:
        return str(e), 500


@app.route("/v2/get-random-short-video")
def get_random_short_video():
    database = ProductionDatabase()
    short_videos_embedded = database.read_table('videos_vectors_stored')
    video_id = random.choice(list(short_videos_embedded['video_id']))
    return video_id


@app.route("/v2/get-short-and-segments")
def get_short_and_segments():
    database = ProductionDatabase()
    short_videos_embedded = database.read_table('videos_vectors_stored')
    video_id = random.choice(list(short_videos_embedded['video_id']))
    qdrant = QdrantClient(os.getenv('QDRANT_LOCATION'))

    qdrant_query = qdrant.scroll(
        collection_name="videos_and_segments",
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="video_id",
                    match=models.MatchValue(value=video_id),
                ),
            ]
        ),
        with_vectors=True
    )

    if len(qdrant_query) == 0 or len(qdrant_query[0]) == 0:
        return jsonify({'error': 'QDRANT: Query returned no entries', 'video_id': video_id})

    query_doc = qdrant_query[0][0]

    response = qdrant.search(
        collection_name="videos_and_segments",
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="channel_id",
                    match=models.MatchValue(
                        value=query_doc.payload['channel_id'],
                    ),
                ),
                models.FieldCondition(
                    key="is_segment",
                    match=models.MatchValue(
                        value=True,
                    ),
                )
            ]
        ),
        search_params=models.SearchParams(hnsw_ef=128, exact=False),
        query_vector=query_doc.vector,
        limit=5,
    )

    if len(response) == 0:
        return jsonify({'error': f'QDRANT: No related videos for id {video_id}', 'video_id': video_id})
    else:
        similar_videos = [{**{'score': res.score}, **res.payload} for res in response]

        return jsonify({
            "search_video_id": video_id,
            'search_results': similar_videos
        })


@app.route("/")
def main_route():
    return "Viranova Backend"


if __name__ == '__main__':
    app.run(port=5000, debug=False)
