import ast
import os
import subprocess

from routes.temporal_segmentation import generate_test_audio
from services.bounding_box_services import smooth_bounding_boxes
from services.verify_video_document import parse_and_verify_short
from services.add_text_to_video_service import AddTextToVideoService
from services.firebase import FirebaseService
import cv2
import tempfile
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

    diff, last_frame, fps = video_analyser.get_differences(temp_file)
    cuts = video_analyser.get_camera_cuts(diff)

    firebase_services.update_document(
        "shorts",
        short_id,
        {
            'cuts': cuts,
            "visual_difference": json.dumps({ "frame_differences": diff }),
            "total_frame_count": last_frame,
            "fps": fps
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

        segment_bounding_boxes = smooth_bounding_boxes(segment_bounding_boxes, window_size=max(int(len(segment_bounding_boxes) / 5), 1))
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


def handle_operations_from_logs(logs, words):
    # If update also update in temporal segmentation
    delete_operations = [i for i in logs if i['type'] == "delete"]
    delete_positions = [{'start': i['start_index'], 'end': i['end_index']} for i in delete_operations]

    for word in words:
        word['position'] = "keep"

    for operation in delete_positions:
        for i in range(operation['start'], operation['end'] + 1):
            words[i]['position'] = 'delete'


    # Apply operations
    output_words = []
    for word in words:
        if word['position'] == 'delete':
            continue
        if word['position'] == 'keep':
            output_words.append(word)

    return output_words

def merge_consecutive_cuts(cuts):
    if not cuts:
        return []

    # Start with the first cut
    merged_cuts = [cuts[0]]

    for current_start, current_end in cuts[1:]:
        last_start, last_end = merged_cuts[-1]

        # If the current start time is the same as the last end time, merge them
        if current_start == last_end:
            merged_cuts[-1] = (last_start, current_end)  # Extend the last segment
        else:
            merged_cuts.append((current_start, current_end))

    return merged_cuts


def adjust_timestamps(merge_cuts, words, start_time):
    adjusted_words = []
    cumulative_offset = 0
    current_cut_index = 0
    for word in words:
        word_start = word['start_time'] - start_time
        word_end = word['end_time'] - start_time
        while current_cut_index < len(merge_cuts) and word_end > merge_cuts[current_cut_index][1]:
            cumulative_offset += merge_cuts[current_cut_index][1] - merge_cuts[current_cut_index][0]
            current_cut_index += 1
        if current_cut_index >= len(merge_cuts):
            break
        if merge_cuts[current_cut_index][0] <= word_start <= merge_cuts[current_cut_index][1]:
            adjusted_word = word.copy()
            adjusted_word['start_time'] = round(word_start - merge_cuts[current_cut_index][0] + cumulative_offset, 3)
            adjusted_word['end_time'] = round(word_end - merge_cuts[current_cut_index][0] + cumulative_offset, 3)
            adjusted_words.append(adjusted_word)
    return adjusted_words


import subprocess
import os

def add_audio_to_video(video_path, audio_path):
    # Generate output video path by adding "_with_audio" before the extension
    output_path = video_path.rsplit('.', 1)[0] + '_with_audio.mp4'

    # Command to add audio to video using ffmpeg
    command = [
        'ffmpeg',
        '-i', video_path,    # Input video file
        '-i', audio_path,    # Input audio file
        '-c:v', 'copy',      # Copy video as is
        '-c:a', 'aac',       # Encode audio to AAC
        '-strict', 'experimental',
        output_path          # Output video file
    ]

    # Run the command with subprocess
    subprocess.run(command, check=True)

    # Delete the temporary files if the merge was successful
    os.remove(video_path)
    os.remove(audio_path)

    return output_path

@spacial_segmentation.route("/create-cropped-video/<short_id>")
def create_cropped_video(short_id):
    firebase_service = FirebaseService()
    short_doc = firebase_service.get_document("shorts", short_id)
    text_service = AddTextToVideoService()

    if not "short_clipped_video" in short_doc.keys():
        print("Clipped video doesn't exist")
        return "Failed - No clipped video"

    clipped_location = short_doc['short_clipped_video']
    temp_clipped_file = firebase_service.download_file_to_temp(clipped_location)

    if not "bounding_boxes" in short_doc.keys():
        print("Bounding boxes do not exist")
        return "Failed - No bounding boxes"

    bounding_boxes = json.loads(short_doc['bounding_boxes'])['boxes']
    _, output_path = tempfile.mkstemp(suffix='.mp4')

    cap = cv2.VideoCapture(temp_clipped_file)
    if not cap.isOpened():
        print("Error: Could not open video.")
        exit()

    # Get video properties
    fps = cap.get(cv2.CAP_PROP_FPS)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Define the codec

    # Assuming all bounding boxes have the same size, we use the first one to set the output video size
    if bounding_boxes:
        _, _, width, height = bounding_boxes[0]
        # Create a video writer for the output video with the size of the bounding box
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    else:
        print("Error: Bounding box list is empty.")
        exit()

    frame_index = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break  # Break the loop if there are no frames left to read

        if frame_index < len(bounding_boxes):
            x, y, w, h = bounding_boxes[frame_index]
            # Crop the frame using the bounding box
            cropped_frame = frame[y:y + h, x:x + w]
            out.write(cropped_frame)
        else:
            print(f"No bounding box for frame {frame_index}, skipping.")

        frame_index += 1

    # Release everything when done
    cap.release()
    out.release()

    COLOUR = (13, 255, 0)
    SHADOW_COLOUR = (192, 255, 189)
    LOGO = "ViraNova"

    if 'short_title_top' in short_doc.keys():
        output_path = text_service.add_text_centered(output_path, short_doc['short_title_top'].upper(), 1,
                                                     thickness='Bold', color=(255, 255, 255), shadow_color=(0, 0, 0),
                                                     shadow_offset=(1, 1), outline=True, outline_color=(0, 0, 0),
                                                     outline_thickness=1, offset=(0, 0.2))

    if 'short_title_bottom' in short_doc.keys():
        output_path = text_service.add_text_centered(output_path, short_doc['short_title_bottom'].upper(), 1, thickness='Bold',
                                                 color=COLOUR, shadow_color=SHADOW_COLOUR,
                                                 shadow_offset=(1, 1), outline=False, outline_color=(0, 0, 0),
                                                 outline_thickness=1, offset=(0, 0.23))

    output_path = text_service.add_text_centered(output_path, LOGO, 0.8,
                                                 thickness='Bold',
                                                 color=COLOUR, shadow_color=(0,0,0),
                                                 shadow_offset=(1, 1), outline=False, outline_color=(0, 0, 0),
                                                 outline_thickness=1, offset=(0, 0.1))

    add_transcript = True
    if add_transcript:
        segment_document = firebase_service.get_document('topical_segments', short_doc['segment_id'])

        segment_document_words = ast.literal_eval(segment_document['words'])
        print("Read Segment Words")
        logs = short_doc['logs']
        words_to_handle = handle_operations_from_logs(logs, segment_document_words)
        words_to_handle = [
            {**word, 'end_time': min(word['end_time'], words_to_handle[i + 1]['start_time'])}
            if i + 1 < len(words_to_handle) else word
            for i, word in enumerate(words_to_handle)
        ]
        start_time = segment_document_words[0]['start_time']
        keep_cuts = [(round(i['start_time'] - start_time, 3), round(i['end_time'] - start_time, 3)) for i in
                     words_to_handle]

        merge_cuts = merge_consecutive_cuts(keep_cuts)

        adjusted_words_to_handle = adjust_timestamps(merge_cuts, words_to_handle, start_time)

        max_chars = 15
        combined_text = ""
        current_start_time = adjusted_words_to_handle[0]['start_time']
        current_end_time = adjusted_words_to_handle[0]['end_time']
        texts = []
        start_times = []
        end_times = []

        for word in adjusted_words_to_handle:
            word_text = word['word']
            start_time = word['start_time']
            end_time = word['end_time']

            if len(combined_text) + len(word_text) <= max_chars:
                if combined_text:
                    combined_text += " "
                combined_text += word_text
                current_end_time = end_time
            else:
                start_times.append(current_start_time)
                end_times.append(current_end_time)
                texts.append(combined_text)

                # Reset Variables
                combined_text = word_text
                current_start_time = start_time
                current_end_time = end_time

        # update start and end_times  relation to that new clipped video
        output_path = text_service.add_transcript(
            input_path=output_path,
            texts=[i.upper() for i in texts],
            start_times=start_times,
            end_times=end_times,
            font_scale=1,
            thickness='Bold',
            color=(255, 255, 255),
            shadow_color=(0, 0, 0),
            shadow_offset=(1, 1),
            outline=True,
            outline_color=(0, 0, 0),
            outline_thickness=2,
            offset=(0, 0),
        )


    generate_test_audio(short_id)

    firebase_service = FirebaseService()
    short_doc = firebase_service.get_document("shorts", short_id)

    audio_path = firebase_service.download_file_to_temp(short_doc['temp_audio_file'], short_doc['temp_audio_file'].split(".")[-1])
    output_path = add_audio_to_video(output_path, audio_path)

    # Create an output path
    destination_blob_name = "finished-short/" + short_id + "-" + "".join(clipped_location.split("/")[1:])
    firebase_service.upload_file_from_temp(output_path, destination_blob_name)

    firebase_service.update_document("shorts", short_id, {"finished_short_location": destination_blob_name, "finished_short_fps": fps})

    print("Finished Video!")
    os.remove(temp_clipped_file)

    return "Done"


