import itertools
import numpy as np

from tests.topical_segmentation.evaluate_topical_segmentation import evaluate_segmentation


def fine_tune_parameters(fixed_length_transcripts, reference_boundaries, video_id, update_progress,
                         update_progress_message):
    std_values = np.arange(0.5, 2.1, 0.1)
    threshold_multipliers = np.arange(0.5, 2.1, 0.1)

    best_score = float('inf')
    best_params = None
    best_segments = None

    total_iterations = len(std_values) * len(threshold_multipliers)
    current_iteration = 0

    for std, threshold_mult in itertools.product(std_values, threshold_multipliers):
        current_iteration += 1
        progress = (current_iteration / total_iterations) * 100
        update_progress(progress)
        update_progress_message(f"Testing parameters: std={std:.2f}, threshold_mult={threshold_mult:.2f}")

        # Calculate boundaries using current parameters
        embeddings = calculate_embeddings(fixed_length_transcripts)  # You need to import this function
        angular_distances = calculate_angular_distances(embeddings)  # You need to import this function
        mean_angular_distance = np.mean(angular_distances)
        std_deviation = np.std(angular_distances)
        threshold = mean_angular_distance + threshold_mult * std_deviation

        boundaries = extract_boundaries(angular_distances, threshold)

        # Create segments
        segments = create_segments(fixed_length_transcripts, boundaries, video_id, lambda x: None, lambda x: None)

        # Evaluate segmentation
        hypothesis_boundaries = ''.join(['1' if b else '0' for b in boundaries])
        evaluation = evaluate_segmentation(reference_boundaries, hypothesis_boundaries, segments)

        # Update best parameters if current score is better
        if evaluation['combined_score'] < best_score:
            best_score = evaluation['combined_score']
            best_params = {'std': std, 'threshold_mult': threshold_mult}
            best_segments = segments

    return best_params, best_segments, best_score