import numpy as np
from serverless_backend.services.verify_video_document import parse_and_verify_video
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.open_ai import OpenAIService
from flask import Blueprint, jsonify
import json

topical_segmentation = Blueprint("topical_segmentation", __name__)


# Constants
TOTAL_AVAILABLE_TOKENS = 8000  # Lower Bound
TOKEN_SIZE = 3
AVERAGE_ENGLISH_WORD_LENGTH = 8
FIXED_SEGMENT_LENGTH = 43
AVERAGE_CHAR_SEGMENT = FIXED_SEGMENT_LENGTH * AVERAGE_ENGLISH_WORD_LENGTH
SEGMENTS_TO_SEND_IN_PARALLEL = int((TOTAL_AVAILABLE_TOKENS * TOKEN_SIZE) / AVERAGE_CHAR_SEGMENT)


# Helper Functions
def extract_boundaries(angular_distances, threshold):
    # Convert angular distances to a binary segmentation based on the threshold
    binary_segmentation = [1 if distance > threshold else 0 for distance in angular_distances]
    return binary_segmentation


def cosine_similarity(v1, v2):
    """Compute the cosine similarity between two vectors."""
    # Normalize the vectors to have unit length
    v1_normalized = v1 / np.linalg.norm(v1)
    v2_normalized = v2 / np.linalg.norm(v2)
    # Compute the cosine similarity
    return np.dot(v1_normalized, v2_normalized)


def angular_distance(similarity):
    """Convert cosine similarity to angular distance in degrees."""
    # Clip the similarity to ensure it's within the valid range for arccos
    similarity_clipped = np.clip(similarity, -1, 1)
    try:
        # Compute the angular distance in radians
        angle_rad = np.arccos(similarity_clipped)
        # Convert to degrees for easier interpretation
        angle_deg = np.degrees(angle_rad)
        return angle_deg
    except Exception as e:
        print(f"Error computing angular distance: {e}")
        return 0


def calculate_boundaries_for_segments(subset_embeddings, update_progress):
    # Optimal Values for this video where:
    # Threshold = mean + 1.05 * std
    std = 0.7

    # Compute angular distance between consecutive embeddings
    angular_distances = []

    for i in range(len(subset_embeddings) - 1):
        update_progress(i / (len(subset_embeddings) - 1) * 100)
        sim = cosine_similarity(subset_embeddings[i], subset_embeddings[i + 1])
        ang_dist = angular_distance(sim)

        # Check if ang_dist is NaN, and if so, append None
        if np.isnan(ang_dist):
            angular_distances.append(None)
        elif ang_dist == 0:
            angular_distances.append(None)
        else:
            angular_distances.append(ang_dist)

    # Now calculate the mean from the valid angular distances only
    valid_distances = [d for d in angular_distances if d is not None]

    if valid_distances:
        mean_angular_distance = np.mean(valid_distances)
        std_deviation = np.std(valid_distances)
    else:
        # Handle the case where valid_distances is empty
        mean_angular_distance = 0
        std_deviation = 0

    # Replace None values with the mean angular distance
    angular_distances = [d if d is not None else mean_angular_distance for d in angular_distances]

    return extract_boundaries(angular_distances, mean_angular_distance + std_deviation * std)


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


def get_transcript_topic_boundaries(embeddings, update_progress, update_progress_message):
    update_progress_message("Extracting the Transcript Boundaries")
    boundaries = calculate_boundaries_for_segments(embeddings, update_progress)
    return boundaries


def create_segments(fixed_length_transcripts, boundaries, video_id, update_progress, update_progress_message):
    segments = []
    current_segment_transcripts = []
    current_words = []
    earliest_start_time = None
    latest_end_time = None

    update_progress_message("Creating new segments")

    for i, (transcript, boundary) in enumerate(zip(fixed_length_transcripts, boundaries)):
        # Initialize for the first segment or new segment
        update_progress(i / (len(fixed_length_transcripts) - 1) * 100)

        if boundary == 1 or i == 0:
            if current_segment_transcripts:
                # Save the previous segment
                segment = {
                    'earliest_start_time': earliest_start_time,
                    'latest_end_time': latest_end_time,
                    'start_index': min([i['index'] for i in current_words]),
                    'end_index': max([i['index'] for i in current_words]),
                    'video_id': video_id,  # This might need to be set differently
                    'index': len(segments),
                    'segment_status': "Topical Segment Created",
                    'previous_segment_status': "Topical Segment Created",
                    'transcript': " ".join(current_segment_transcripts),
                    'words': str(current_words)
                }
                segments.append(segment)
                current_segment_transcripts = []
                current_words = []

            # Reset for new segment
            earliest_start_time = transcript['start_time']
            latest_end_time = transcript['end_time']
            current_segment_transcripts.append(transcript['transcript'])
            current_words.extend(transcript['words'])
        else:
            # Continue with the current segment
            latest_end_time = max(latest_end_time, transcript['end_time'])
            current_segment_transcripts.append(transcript['transcript'])
            current_words.extend(transcript['words'])

    # Add the last segment if there are remaining transcripts
    if current_segment_transcripts:
        segment = {
            'earliest_start_time': earliest_start_time,
            'latest_end_time': latest_end_time,
            'start_index': min([i['index'] for i in current_words]),
            'end_index': max([i['index'] for i in current_words]),
            'video_id': video_id,
            'index': len(segments),
            'segment_status': "Topical Segment Created",
            'previous_segment_status': "Topical Segment Created",
            'transcript': " ".join(current_segment_transcripts),
            'words': str(current_words)
        }
        segments.append(segment)

    return segments


# Routes
def reformat_transcripts(transcripts):
    # Sort the transcripts based on the 'index' key
    sorted_transcripts = sorted(transcripts, key=lambda x: x['index'])
    # Initialize a new list to hold all the words with updated indices
    all_words = []
    current_word_index = 0  # This will keep track of the overall index of words across all transcripts
    # Iterate over each transcript in the sorted order
    for transcript in sorted_transcripts:
        words = transcript['words']
        updated_words = []  # This will store updated words for the current transcript
        # Iterate over each word in the current transcript
        for word in words:
            updated_word = word.copy()  # Copy the original word dictionary
            updated_word['index'] = current_word_index  # Assign the new index
            updated_words.append(updated_word)  # Add the updated word to the list
            current_word_index += 1  # Increment the global word index
        # Replace the old words list in the transcript with the updated one
        transcript['words'] = updated_words
    return sorted_transcripts  # Return the modified list of transcripts

@topical_segmentation.route("/v1/extract-topical-segments/<video_id>", methods=['GET'])
def extract_topical_segments(video_id: str):
    try:
        firebase_service = FirebaseService()
        open_ai_service = OpenAIService()
        video_document = firebase_service.get_document("videos", video_id)
        is_valid_document, error_message = parse_and_verify_video(video_document)
        update_progress_message = lambda x: firebase_service.update_document('videos', video_id, {'progressMessage': x})
        update_progress = lambda x: firebase_service.update_document('videos', video_id, {'processingProgress': x})

        if not is_valid_document:
            return jsonify({
                "status": "error",
                "data": {"video_id": video_id, "error": error_message},
                "message": "Failed to perform topical segmentation"
            }), 400

        update_progress(0)
        update_progress_message("Determining the video topics...")

        # Delete Previous Topical Segments
        previous_topical_segments = firebase_service.query_topical_segments_by_video_id(video_id)
        if previous_topical_segments:
            firebase_service.batch_delete_documents('topical_segments',
                                                    [seg['id'] for seg in previous_topical_segments])

        transcripts = firebase_service.query_transcripts_by_video_id_with_words(video_id)
        transcripts = reformat_transcripts(transcripts)

        update_progress_message("Extracting Transcript Words")
        words = [word for transcript in transcripts for word in transcript['words']]

        num_transcripts = len(words) // FIXED_SEGMENT_LENGTH + (1 if len(words) % FIXED_SEGMENT_LENGTH != 0 else 0)
        segmented_transcripts = [words[i * FIXED_SEGMENT_LENGTH:(i + 1) * FIXED_SEGMENT_LENGTH] for i in
                                 range(num_transcripts)]

        fixed_length_segments = [
            {
                'start_time': min((w['start_time'] for w in segment if w['start_time'] is not None), default=None),
                'end_time': max((w['end_time'] for w in segment if w['end_time'] is not None), default=None),
                'start_index': min(w['index'] for w in segment),
                'end_index': max(w['index'] for w in segment),
                'transcript': ' '.join(w['word'] for w in segment),
                'words': segment,
            }
            for segment in segmented_transcripts
        ]

        update_progress_message("Getting text embeddings... This might take a while...")
        try:
            embeddings = open_ai_service.get_embeddings_parallel([seg['transcript'] for seg in fixed_length_segments],
                                                                 SEGMENTS_TO_SEND_IN_PARALLEL,
                                                                 update_progress=update_progress)
        except Exception as e:
            return jsonify({
                "status": "error",
                "data": {"video_id": video_id, "error": str(e)},
                "message": "Failed to generate embeddings"
            }), 500

        update_progress_message("Finding topic changes")
        boundaries = get_transcript_topic_boundaries(embeddings, update_progress, update_progress_message)
        segments = create_segments(fixed_length_segments, boundaries, video_id, update_progress,
                                   update_progress_message)

        update_progress_message("Uploading segments to database")
        segments_to_add = []
        for index, segment in enumerate(segments):
            update_progress((index + 1) / len(segments) * 100)
            segment['words'] = json.dumps(segment['words'])  # Convert words to JSON string
            segments_to_add.append(segment)

        # Use the new batch_add_documents method
        firebase_service.batch_add_documents("topical_segments", segments_to_add)

        update_progress_message("Finished Segmenting Video!")
        firebase_service.update_document('videos', video_id, {'status': "Summarizing Segments"})

        return jsonify({
            "status": "success",
            "data": {"video_id": video_id, "segment_count": len(segments)},
            "message": "Successfully performed topical segmentation"
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "data": {"video_id": video_id, "error": str(e)},
            "message": "Failed to perform topical segmentation"
        }), 500
