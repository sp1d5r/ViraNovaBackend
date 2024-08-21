from firebase_admin import firestore
import firebase_admin
import numpy as np
from scipy.stats import hmean

# Initialize Firebase (make sure you have the correct credentials set up)
if not firebase_admin._apps:
    firebase_admin.initialize_app()

db = firestore.client()


def get_segments_from_firebase(video_id):
    """
    Retrieve segments for a given video ID from Firebase.
    """
    segments = db.collection('topical_segments').where('video_id', '==', video_id).order_by('index').get()
    return [segment.to_dict() for segment in segments]


def prepare_boundaries(timestamps, duration, granularity=1):
    """
    Prepare a boundary string based on the timestamps.
    granularity is the number of seconds each character in the string represents.
    """
    boundaries = ['0'] * (int(duration) // granularity)
    for timestamp in timestamps:
        index = int(timestamp) // granularity
        if index < len(boundaries):
            boundaries[index] = '1'
    return ''.join(boundaries)


def evaluate_segmentation(reference, hypothesis, segments):
    pk = pk_measure(reference, hypothesis)
    wd = windowdiff(reference, hypothesis)
    seg_ratio = segmentation_ratio(reference, hypothesis)
    avg_duration = average_segment_duration(segments)

    # Compute a combined score (higher is better)
    combined_score = hmean([1 - pk, 1 - wd, 1 / (1 + abs(1 - seg_ratio))])

    return {
        'pk': pk,
        'windowdiff': wd,
        'segmentation_ratio': seg_ratio,
        'average_duration': avg_duration,
        'combined_score': combined_score
    }


# pk_measure, windowdiff, segmentation_ratio, and average_segment_duration functions remain the same

def evaluate_video_segmentation(video_id, reference_timestamps):
    """
    Evaluate the segmentation for a specific video using reference timestamps.
    """
    # Get segments from Firebase
    segments = get_segments_from_firebase(video_id)

    if not segments:
        return {"error": "No segments found for this video ID"}

    # Get video duration (assuming the last segment ends at the video's end)
    video_duration = segments[-1]['latest_end_time']

    # Prepare reference boundaries
    reference_boundaries = prepare_boundaries(reference_timestamps, video_duration)

    # Prepare hypothesis boundaries
    hypothesis_timestamps = [seg['earliest_start_time'] for seg in segments if seg['index'] > 0]
    hypothesis_boundaries = prepare_boundaries(hypothesis_timestamps, video_duration)

    # Ensure reference and hypothesis have the same length
    min_length = min(len(reference_boundaries), len(hypothesis_boundaries))
    reference_boundaries = reference_boundaries[:min_length]
    hypothesis_boundaries = hypothesis_boundaries[:min_length]

    # Evaluate segmentation
    evaluation = evaluate_segmentation(reference_boundaries, hypothesis_boundaries, segments)

    return evaluation


# Example usage
if __name__ == "__main__":
    video_id = "your_video_id_here"
    reference_timestamps = [0, 120, 360, 540, 720]  # Example timestamps in seconds

    results = evaluate_video_segmentation(video_id, reference_timestamps)
    print(f"Evaluation results for video {video_id}:")
    for metric, value in results.items():
        print(f"{metric}: {value}")