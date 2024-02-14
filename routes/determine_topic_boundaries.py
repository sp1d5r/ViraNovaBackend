import numpy as np

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
    std = 1.05

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

def get_transcript_topic_boundaries(embeddings, update_progress, update_progress_message):
    update_progress_message("Extracting the Transcript Boundaries")
    boundaries = calculate_boundaries_for_segments(embeddings, update_progress)
    return boundaries


def create_segments(transcripts, boundaries, update_progress, update_progress_message):
    segments = []
    current_segment_transcripts = []
    start_index = 0
    earliest_start_time = None
    latest_end_time = None
    video_id = None

    update_progress_message("Creating new segments")

    for i, (transcript, boundary) in enumerate(zip(transcripts, boundaries)):
        # Initialize for the first segment or new segment
        update_progress(i/(len(transcripts)-1) * 100)
        if boundary == 1 or i == 0:
            if current_segment_transcripts:
                # Save the previous segment
                segment = {
                    'earliest_start_time': earliest_start_time,
                    'latest_end_time': latest_end_time,
                    'start_index': start_index,
                    'end_index': i - 1,
                    'video_id': video_id,
                    'index': len(segments),
                    'transcript': "\n".join(current_segment_transcripts)
                }
                segments.append(segment)
                current_segment_transcripts = []

            # Reset for new segment
            start_index = i
            earliest_start_time = transcript['earliest_start_time']
            latest_end_time = transcript['latest_end_time']
            video_id = transcript['video_id']
            current_segment_transcripts.append(transcript['transcript'])
        else:
            # Continue with the current segment
            latest_end_time = max(latest_end_time, transcript['latest_end_time'])
            current_segment_transcripts.append(transcript['transcript'])

        # Update times across segments
        if earliest_start_time is None or transcript['earliest_start_time'] < earliest_start_time:
            earliest_start_time = transcript['earliest_start_time']
        if latest_end_time is None or transcript['latest_end_time'] > latest_end_time:
            latest_end_time = transcript['latest_end_time']

    # Add the last segment if there are remaining transcripts
    if current_segment_transcripts:
        segment = {
            'earliest_start_time': earliest_start_time,
            'latest_end_time': latest_end_time,
            'start_index': start_index,
            'end_index': len(transcripts) - 1,
            'video_id': video_id,
            'index': len(segments),
            'transcript': "\n".join(current_segment_transcripts)
        }
        segments.append(segment)

    return segments

