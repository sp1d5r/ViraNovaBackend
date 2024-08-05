import ast
from datetime import datetime
from serverless_backend.routes.generate_test_audio import generate_test_audio_for_short
from serverless_backend.services.bounding_box_services import smooth_bounding_boxes
from serverless_backend.services.handle_operations_from_logs import handle_operations_from_logs
from serverless_backend.services.verify_video_document import parse_and_verify_short
from serverless_backend.services.add_text_to_video_service import AddTextToVideoService
from serverless_backend.services.video_audio_merger import VideoAudioMerger
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.bounding_box_generator.sliding_window_box_generation import SlidingWindowBoundingBoxGenerator
from serverless_backend.services.video_analyser.video_analyser import VideoAnalyser
import cv2
import tempfile
from flask import Blueprint, jsonify
import json


spacial_segmentation = Blueprint("spacial_segmentation", __name__)

@spacial_segmentation.route("/v1/determine-boundaries/<short_id>", methods=['GET'])
def determine_boundaries(short_id):
    try:
        firebase_services = FirebaseService()
        video_analyser = VideoAnalyser()
        short_doc = firebase_services.get_document("shorts", short_id)
        update_progress = lambda x: firebase_services.update_document("shorts", short_id, {"update_progress": x})
        update_message = lambda x: firebase_services.update_document("shorts", short_id,
                                                                    {"progress_message": x, "last_updated": datetime.now()})

        update_message("Retrieved the document")
        firebase_services.update_document("shorts", short_id, {"pending_operation": True})
        update_progress(20)
        valid_short, error_message = parse_and_verify_short(short_doc)

        if not valid_short:
            firebase_services.update_document("shorts", short_id, {"pending_operation": False})
            return jsonify(
                {
                    "status": "error",
                    "data": {
                        "short_id": short_id,
                        "error": error_message
                    },
                    "message": "Failed to find camera cuts in video"
                }), 400

        update_message("Downloading the clipped video")
        update_progress(30)
        video_path = short_doc['short_clipped_video']

        if video_path is None:
            firebase_services.update_document("shorts", short_id, {"pending_operation": False})
            return jsonify(
                {
                    "status": "error",
                    "data": {
                        "short_id": short_id,
                        "error":"No video clipped yet..."
                    },
                    "message": "Failed to find camera cuts in video"
                }), 400

        update_progress(50)
        update_message("Getting temporary file")
        temp_file = firebase_services.download_file_to_temp(video_path)
        update_progress_diff = lambda x: update_progress(50 + 50 * (x/100))
        update_message("Calculating frame difference")
        diff, last_frame, fps, height, width = video_analyser.get_differences(temp_file, update_progress_diff)
        cuts = video_analyser.get_camera_cuts(diff)
        update_message("Completed Download")
        firebase_services.update_document(
            "shorts",
            short_id,
            {
                'cuts': cuts,
                "visual_difference": json.dumps({ "frame_differences": diff }),
                "total_frame_count": last_frame,
                "fps": fps,
                "height": height,
                "width": width,
                "short_status": "Get Bounding Boxes",
            }
        )

        firebase_services.update_document("shorts", short_id, {"pending_operation": False})
        return jsonify(
            {
                "status": "success",
                "data": {
                    "short_id": short_id,
                    'cuts': cuts,
                    "visual_difference": json.dumps({ "frame_differences": diff }),
                    "total_frame_count": last_frame,
                    "fps": fps,
                    "height": height,
                    "width": width,
                },
                "message": "Successfully determined camera cuts in video"
            }), 200
    except Exception as e:
        return jsonify(
            {
                "status": "error",
                "data": {
                    "short_id": short_id,
                    "error": str(e)
                },
                "message": "Failed to find camera cuts in video"
            }), 400



@spacial_segmentation.route("/v1/get-bounding-boxes/<short_id>", methods=['GET'])
def get_bounding_boxes(short_id):
    try:
        firebase_services = FirebaseService()
        short_doc = firebase_services.get_document("shorts", short_id)
        bounding_box_generator = SlidingWindowBoundingBoxGenerator()
        update_progress = lambda x: firebase_services.update_document("shorts", short_id, {"update_progress": x})
        update_message = lambda x: firebase_services.update_document("shorts", short_id,
                                                                     {"progress_message": x,
                                                                      "last_updated": datetime.now()})

        update_message("Retrieved the document")
        firebase_services.update_document("shorts", short_id, {"pending_operation": True})


        update_message("Checking short document is correct")
        if short_doc["short_video_saliency"] is None:
            firebase_services.update_document("shorts", short_id, {"pending_operation": False})
            return jsonify(
                {
                    "status": "error",
                    "data": {
                        "short_id": short_id,
                        "error": "Short video does not have saliency"
                    },
                    "message": "Failed to find bounding boxes"
                }), 400

        update_message("Downloading Saliency Video...")
        update_progress(20)
        short_video_saliency = firebase_services.download_file_to_temp(short_doc['short_video_saliency'])

        if 'cuts' not in short_doc.keys():
            determine_boundaries(short_id)

        short_doc = firebase_services.get_document("shorts", short_id)
        cuts = short_doc['cuts']
        update_message("Processing video cuts...")
        update_progress(30)

        update_message("Adjusted Frames")
        skip_frames = 5
        fixed_cuts = [i//skip_frames for i in cuts]
        last_frame = short_doc['total_frame_count'] // skip_frames
        all_bounding_boxes = []
        evaluated_saliency = []

        start_frame = 0

        update_message("Calculating Bounding Boxes")
        update_temp_progress= lambda x, start, length: update_progress(start + (length * (x/100)))
        for index, end_frame in enumerate(fixed_cuts):
            bounding_boxes = bounding_box_generator.generate_bounding_boxes(short_video_saliency, start_frame, end_frame)
            evaluate_bounding_box_success = bounding_box_generator.evaluate_saliency(short_video_saliency, bounding_boxes,
                                                                                     start_frame, end_frame)
            all_bounding_boxes.append(bounding_boxes)
            evaluated_saliency.append(evaluate_bounding_box_success)
            start_frame = end_frame + 1
            update_temp_progress(100 * (index/len(fixed_cuts)), 30, 40)

        if fixed_cuts[-1] != last_frame:
            bounding_boxes = bounding_box_generator.generate_bounding_boxes(short_video_saliency, fixed_cuts[-1], last_frame)
            evaluate_bounding_box_success = bounding_box_generator.evaluate_saliency(short_video_saliency, bounding_boxes,
                                                                                     fixed_cuts[-1],
                                                                                     last_frame)
            all_bounding_boxes.append(bounding_boxes)
            evaluated_saliency.append(evaluate_bounding_box_success)
            update_progress(72)

        print(sum([len(i) for i in evaluated_saliency]))

        update_message("Interpolating the missing positions within each segment")
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
            update_temp_progress(100 * (segment_index / len(all_bounding_boxes)), 75, 20)


        integer_boxes = [list(i) for i in all_interpolated_boxes][:short_doc['total_frame_count'] + 1]
        saliency_vals = [float(i) for i in interpolated_saliency][:short_doc['total_frame_count'] + 1]

        print(len(integer_boxes), len(saliency_vals))
        update_message(100)
        firebase_services.update_document("shorts", short_id, {"pending_operation": False})
        firebase_services.update_document(
            "shorts",
            short_id,
            {
                "bounding_boxes": json.dumps({"boxes": integer_boxes}),
                "saliency_values": json.dumps({"saliency_vals": saliency_vals})
            }
        )

        return jsonify(
            {
                "status": "error",
                "data": {
                    "short_id": short_id,
                    "bounding_boxes": json.dumps({"boxes": integer_boxes}),
                    "saliency_values": json.dumps({"saliency_vals": saliency_vals})
                },
                "message": "Successfullly found bounding boxes"
            }), 200
    except Exception as e:
        return jsonify(
            {
                "status": "error",
                "data": {
                    "short_id": short_id,
                    "error": str(e)
                },
                "message": "Failed to find bounding boxes"
            }), 400


def merge_consecutive_cuts(cuts):
    if not cuts:
        return []

    # Start with the first cut, but ensure it doesn't exceed the video duration
    merged_cuts = [(cuts[0][0], cuts[0][1])]

    for current_start, current_end in cuts[1:]:
        last_start, last_end = merged_cuts[-1]

        # Cap the end time to the maximum duration of the video
        current_end = current_end

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

@spacial_segmentation.route("/v1/create-cropped-video/<short_id>", methods=['GET'])
def create_cropped_video(short_id):
    try:
        firebase_service = FirebaseService()
        short_doc = firebase_service.get_document("shorts", short_id)
        text_service = AddTextToVideoService()
        video_audio_merger = VideoAudioMerger()

        update_progress = lambda x: firebase_service.update_document("shorts", short_id, {"update_progress": x})
        update_message = lambda x: firebase_service.update_document("shorts", short_id,
                                                                     {"progress_message": x,
                                                                      "last_updated": datetime.now()})
        update_temp_progress = lambda x, start, length: update_progress(start + (length * (x / 100)))

        update_message("Retrieved the document")
        firebase_service.update_document("shorts", short_id, {"pending_operation": True})

        update_progress(20)
        if not "short_clipped_video" in short_doc.keys():
            update_message("Clipped video doesn't exist")
            firebase_service.update_document("shorts", short_id, {"pending_operation": False})
            return jsonify(
                {
                    "status": "error",
                    "data": {
                        "short_id": short_id,
                        "error": "No clipped video exists"
                    },
                    "message": "Failed to preview video"
                }), 400
        update_message("Accessed the short document")

        clipped_location = short_doc['short_clipped_video']
        update_message("Download the clipped video")
        temp_clipped_file = firebase_service.download_file_to_temp(clipped_location)
        update_progress(30)

        if not "bounding_boxes" in short_doc.keys():
            update_message("Bounding boxes do not exist")
            firebase_service.update_document("shorts", short_id, {"pending_operation": False})
            return jsonify(
                {
                    "status": "error",
                    "data": {
                        "short_id": short_id,
                        "error": "No bounding boxes on short"
                    },
                    "message": "Failed to preview video"
                }), 400

        bounding_boxes = json.loads(short_doc['bounding_boxes'])['boxes']
        _, output_path = tempfile.mkstemp(suffix='.mp4')

        cap = cv2.VideoCapture(temp_clipped_file)
        update_message("Tried to open clipped video")
        if not cap.isOpened():
            update_message("Error: Could not open video.")
            firebase_service.update_document("shorts", short_id, {"pending_operation": False})
            return jsonify(
                {
                    "status": "error",
                    "data": {
                        "short_id": short_id,
                        "error": "Unable to open clipped video"
                    },
                    "message": "Failed to preview video"
                }), 400


        # Get video properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Define the codec

        update_message("Loading in bounding boxes")

        # Assuming all bounding boxes have the same size, we use the first one to set the output video size
        if bounding_boxes:
            _, _, width, height = bounding_boxes[0]
            # Create a video writer for the output video with the size of the bounding box
            out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        else:
            update_message("Error: Bounding box list is empty.")
            firebase_service.update_document("shorts", short_id, {"pending_operation": False})
            exit()

        frame_index = 0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
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
            update_temp_progress((frame_index/total_frames) * 100 ,30,30)

        # Release everything when done
        cap.release()
        out.release()

        COLOUR = (13, 255, 0)
        SHADOW_COLOUR = (192, 255, 189)
        LOGO = "ViraNova"

        if 'short_title_top' in short_doc.keys():
            update_message("Added top text")
            update_progress(65)
            output_path = text_service.add_text_centered(output_path, short_doc['short_title_top'].upper(), 1.7,
                                                         thickness='Bold', color=(255, 255, 255), shadow_color=(0, 0, 0),
                                                         shadow_offset=(1, 1), outline=True, outline_color=(0, 0, 0),
                                                         outline_thickness=1, offset=(0, 0.15))

        if 'short_title_bottom' in short_doc.keys():
            update_message("Added bottom text")
            update_progress(70)
            output_path = text_service.add_text_centered(output_path, short_doc['short_title_bottom'].upper(), 1.7, thickness='Bold',
                                                     color=COLOUR, shadow_color=SHADOW_COLOUR,
                                                     shadow_offset=(1, 1), outline=False, outline_color=(0, 0, 0),
                                                     outline_thickness=1, offset=(0, 0.18))

        output_path = text_service.add_text_centered(output_path, LOGO, 1,
                                                     thickness='Bold',
                                                     color=COLOUR, shadow_color=(0,0,0),
                                                     shadow_offset=(1, 1), outline=False, outline_color=(0, 0, 0),
                                                     outline_thickness=1, offset=(0, 0.1))

        add_transcript = True
        if add_transcript:
            segment_document = firebase_service.get_document('topical_segments', short_doc['segment_id'])

            segment_document_words = ast.literal_eval(segment_document['words'])
            update_message("Read Segment Words")
            update_progress(75)
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

            for index, word in enumerate(adjusted_words_to_handle):
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
                update_message("Added words: " + str(combined_text))
                update_temp_progress(index/len(adjusted_words_to_handle) * 100, 75, 15)

            update_message("Adding transcript to video")
            # update start and end_times  relation to that new clipped video
            output_path = text_service.add_transcript(
                input_path=output_path,
                texts=[i.upper() for i in texts],
                start_times=start_times,
                end_times=end_times,
                font_scale=1.3,
                thickness='Bold',
                color=(255, 255, 255),
                shadow_color=(0, 0, 0),
                shadow_offset=(1, 1),
                outline=True,
                outline_color=(0, 0, 0),
                outline_thickness=2,
                offset=(0, 0),
            )

            update_message("Added transcript")
            update_progress(95)

        update_message("Creating Updated short audio file")
        generate_test_audio_for_short(short_id)
        update_message("Adding audio now")
        firebase_service = FirebaseService()
        short_doc = firebase_service.get_document("shorts", short_id)

        audio_path = firebase_service.download_file_to_temp(short_doc['temp_audio_file'], short_doc['temp_audio_file'].split(".")[-1])
        output_path = add_audio_to_video(output_path, audio_path)

        if "background_audio" in short_doc.keys():
            background_audio = firebase_service.get_document("stock-audio", short_doc['background_audio'])
            temp_audio_location = firebase_service.download_file_to_temp(background_audio['storageLocation'])
            output_path = video_audio_merger.merge_audio_to_video(output_path, temp_audio_location,
                                                                  short_doc['background_percentage'])

        # Create an output path
        update_message("Added output path to short location")
        destination_blob_name = "finished-short/" + short_id + "-" + "".join(clipped_location.split("/")[1:])
        firebase_service.upload_file_from_temp(output_path, destination_blob_name)

        firebase_service.update_document("shorts", short_id, {"finished_short_location": destination_blob_name, "finished_short_fps": fps})

        update_message("Finished Video!")
        firebase_service.update_document("shorts", short_id, {"pending_operation": False})
        os.remove(temp_clipped_file)

        return jsonify(
            {
                "status": "success",
                "data": {
                    "short_id": short_id,
                    "finished_short_location": destination_blob_name,
                    "finished_short_fps": fps
                },
                "message": "Successfully previewed final video"
            }), 200
    except Exception as e:
        return jsonify(
            {
                "status": "error",
                "data": {
                    "short_id": short_id,
                    "error": str(e)
                },
                "message": "Failed to preview video"
            }), 400


