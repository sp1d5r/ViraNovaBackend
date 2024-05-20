from scipy.interpolate import interp1d
import numpy as np
from services.verify_video_document import parse_and_verify_short
from services.firebase import FirebaseService
from flask import Blueprint
from services.video_analyser.video_analyser import VideoAnalyser
from services.bounding_box_generator.sliding_window_box_generation import SlidingWindowBoundingBoxGenerator
import json

spacial_segmentation = Blueprint("spacial_segmentation", __name__)

@spacial_segmentation.route("/determine-boundaries/<short_id>")
def determine_boundaries(short_id):
    firebase_services = FirebaseService()
    video_analyser = VideoAnalyser()
    short_doc = firebase_services.get_document("shorts", short_id)
    valid_short, error_message = parse_and_verify_short(short_doc)

    if not valid_short:
        return 404, error_message

    video_path = short_doc['short_clipped_video']

    if video_path is None:
        return 403, "No video clipped yet..."

    print("Getting temporary file")
    temp_file = firebase_services.download_file_to_temp(video_path)

    diff, last_frame = video_analyser.get_differences(temp_file)
    cuts = video_analyser.get_camera_cuts(diff)

    firebase_services.update_document(
        "shorts",
        short_id,
        {
            'cuts': cuts,
            "visual_difference": json.dumps({ "frame_differences": diff }),
            "total_frame_count": last_frame
        }
    )

    return "Completed"


@spacial_segmentation.route("/get-bounding-boxes/<short_id>")
def get_bounding_boxes(short_id):
    firebase_services = FirebaseService()
    short_doc = firebase_services.get_document("shorts", short_id)
    bounding_box_generator = SlidingWindowBoundingBoxGenerator()


    print("Checking short document is correct")
    if short_doc["short_video_saliency"] is None:
        return 404, "Failed"

    print("Loading Saliency Video")
    short_video_saliency = firebase_services.download_file_to_temp(short_doc['short_video_saliency'])

    if 'cuts' not in short_doc.keys():
        determine_boundaries(short_id)

    short_doc = firebase_services.get_document("shorts", short_id)
    cuts = short_doc['cuts']

    print("Adjusted Frames")
    skip_frames = 5
    fixed_cuts = [i//skip_frames for i in cuts]
    last_frame = short_doc['total_frame_count'] // skip_frames
    all_bounding_boxes = []
    evaluated_saliency = []

    start_frame = 0

    print("Calculating Bounding Boxes")
    for end_frame in fixed_cuts:
        bounding_boxes = bounding_box_generator.generate_bounding_boxes(short_video_saliency, start_frame, end_frame)
        evaluate_bounding_box_success = bounding_box_generator.evaluate_saliency(short_video_saliency, bounding_boxes,
                                                                                 start_frame, end_frame)
        all_bounding_boxes.append(bounding_boxes)
        evaluated_saliency.append(evaluate_bounding_box_success)
        start_frame = end_frame + 1

    if fixed_cuts[-1] != last_frame:
        bounding_boxes = bounding_box_generator.generate_bounding_boxes(short_video_saliency, fixed_cuts[-1], last_frame)
        evaluate_bounding_box_success = bounding_box_generator.evaluate_saliency(short_video_saliency, bounding_boxes,
                                                                                 fixed_cuts[-1],
                                                                                 last_frame)
        all_bounding_boxes.append(bounding_boxes)
        evaluated_saliency.append(evaluate_bounding_box_success)

    print(sum([len(i) for i in evaluated_saliency]))

    print("Interpolating the missing positions within each segment")
    all_interpolated_boxes = []
    interpolated_saliency = []

    for segment_index, bounding_box_segment in enumerate(all_bounding_boxes):
        segment_saliency = evaluated_saliency[segment_index]
        segment_bounding_boxes = []
        segment_saliency_values = []
        for index, bounding_box in enumerate(bounding_box_segment):
            if index == len(bounding_box_segment) - 1:
                segment_bounding_boxes.extend([bounding_box] * 5)
                segment_saliency_values.extend([segment_saliency[index]] * 5)
            else:
                segment_bounding_boxes.append(bounding_box)
                segment_saliency_values.append(segment_saliency[index])

                next_bounding_box = bounding_box_segment[index + 1]
                current_saliency = segment_saliency[index]
                next_saliency_value = segment_saliency[index + 1]

                for i in range(4):
                    new_bounding_box = [abs((i *(bounding_box[0] - next_bounding_box[0])) // 5) + bounding_box[0], bounding_box[1], bounding_box[2],
                                        bounding_box[3]]
                    segment_bounding_boxes.append(new_bounding_box)
                    segment_saliency_values.append(abs(i * (current_saliency - next_saliency_value) // 5) + current_saliency)

        all_interpolated_boxes.extend(segment_bounding_boxes)
        interpolated_saliency.extend(segment_saliency_values)

    integer_boxes = [list(i) for i in all_interpolated_boxes][:short_doc['total_frame_count'] + 1]
    saliency_vals = [float(i) for i in interpolated_saliency][:short_doc['total_frame_count'] + 1]

    print(len(integer_boxes), len(saliency_vals))
    firebase_services.update_document(
        "shorts",
        short_id,
        {
            "bounding_boxes": json.dumps({"boxes": integer_boxes}),
            "saliency_values": json.dumps({"saliency_vals": saliency_vals})
        }
    )

    return "Completed!"





