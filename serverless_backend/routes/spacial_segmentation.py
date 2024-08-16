import ast
from datetime import datetime
from serverless_backend.routes.generate_test_audio import generate_test_audio_for_short
from serverless_backend.services.bounding_box_services import smooth_bounding_boxes
from serverless_backend.services.handle_operations_from_logs import handle_operations_from_logs
from serverless_backend.services.bounding_box_generator.bounding_boxes import BoundingBoxGenerator
from serverless_backend.services.parse_segment_words import parse_segment_words
from serverless_backend.services.verify_video_document import parse_and_verify_short
from serverless_backend.services.add_text_to_video_service import AddTextToVideoService
from serverless_backend.services.video_audio_merger import VideoAudioMerger
from serverless_backend.services.email.brevo_email_service import EmailService
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.video_analyser.video_analyser import VideoAnalyser
from firebase_admin import auth, firestore
import cv2
import tempfile
from flask import Blueprint, jsonify
import json


def get_user_email(uid):
    try:
        user = auth.get_user(uid)
        return user.email
    except Exception as e:
        print(f"Error fetching user data for UID {uid}: {str(e)}")
        return None


spacial_segmentation = Blueprint("spacial_segmentation", __name__)

@spacial_segmentation.route("/v1/determine-boundaries/<request_id>", methods=['GET'])
def determine_boundaries(request_id):
    firebase_services = FirebaseService()
    video_analyser = VideoAnalyser()

    try:
        request_doc = firebase_services.get_document("requests", request_id)
        if not request_doc:
            return jsonify({"status": "error", "message": "Request not found"}), 404

        short_id = request_doc.get('shortId')
        if not short_id:
            return jsonify({"status": "error", "message": "Short ID not found in request"}), 400

        short_doc = firebase_services.get_document("shorts", short_id)
        if not short_doc:
            return jsonify({"status": "error", "message": "Short document not found"}), 404

        def update_progress(progress):
            firebase_services.update_document("shorts", short_id, {"update_progress": progress})
            firebase_services.update_document("requests", request_id, {"progress": progress})

        def update_message(message):
            firebase_services.update_document("shorts", short_id, {
                "progress_message": message,
                "last_updated": firestore.firestore.SERVER_TIMESTAMP
            })
            firebase_services.update_message(request_id, message)

        update_message("Retrieved the document")
        firebase_services.update_document("shorts", short_id, {"pending_operation": True})
        update_progress(20)

        valid_short, error_message = parse_and_verify_short(short_doc)

        if not valid_short:
            update_message(f"Invalid short document: {error_message}")
            firebase_services.update_document("shorts", short_id, {"pending_operation": False})
            return jsonify({
                "status": "error",
                "data": {
                    "request_id": request_id,
                    "short_id": short_id,
                    "error": error_message
                },
                "message": "Failed to find camera cuts in video"
            }), 400

        update_message("Downloading the clipped video")
        update_progress(30)
        video_path = short_doc.get('short_clipped_video')

        if video_path is None:
            error_message = "No video clipped yet..."
            update_message(error_message)
            firebase_services.update_document("shorts", short_id, {"pending_operation": False})
            return jsonify({
                "status": "error",
                "data": {
                    "request_id": request_id,
                    "short_id": short_id,
                    "error": error_message
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
                "pending_operation": False
            }
        )

        update_message("Successfully determined camera cuts in video")
        update_progress(100)

        firebase_services.create_short_request(
            "v1/get-bounding-boxes",
            short_id,
            request_doc.get('uid', 'SERVER REQUEST')
        )

        return jsonify({
            "status": "success",
            "data": {
                "request_id": request_id,
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
        error_message = f"Failed to find camera cuts in video: {str(e)}"
        update_message(error_message)
        firebase_services.update_document("shorts", short_id, {"pending_operation": False})
        return jsonify({
            "status": "error",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
                "error": str(e)
            },
            "message": error_message
        }), 500



@spacial_segmentation.route("/v1/get-bounding-boxes/<request_id>", methods=['GET'])
def get_bounding_boxes(request_id):
    firebase_services = FirebaseService()
    try:
        request_doc = firebase_services.get_document("requests", request_id)
        if not request_doc:
            return jsonify({"status": "error", "message": "Request not found"}), 404

        short_id = request_doc.get('shortId')
        if not short_id:
            return jsonify({"status": "error", "message": "Short ID not found in request"}), 400

        short_doc = firebase_services.get_document("shorts", short_id)
        if not short_doc:
            return jsonify({"status": "error", "message": "Short document not found"}), 404

        bounding_box_generator = BoundingBoxGenerator(step_size=10)

        def update_progress(progress):
            firebase_services.update_document("shorts", short_id, {"update_progress": progress})
            firebase_services.update_document("requests", request_id, {"progress": progress})

        def update_message(message):
            firebase_services.update_document("shorts", short_id, {
                "progress_message": message,
                "last_updated": firestore.firestore.SERVER_TIMESTAMP
            })
            firebase_services.update_message(request_id, message)

        auto_generate = short_doc.get('auto_generate', False)

        update_message("Retrieved the document")
        firebase_services.update_document("shorts", short_id, {"pending_operation": True})

        update_message("Checking short document is correct")
        if short_doc.get("short_video_saliency") is None:
            error_message = "Short video does not have saliency"
            update_message(error_message)
            firebase_services.update_document("shorts", short_id, {
                "pending_operation": False,
                "auto_generate": False
            })
            return jsonify({
                "status": "error",
                "data": {"request_id": request_id, "short_id": short_id, "error": error_message},
                "message": "Failed to find bounding boxes"
            }), 400

        update_message("Downloading Saliency Video...")
        update_progress(20)
        short_video_saliency = firebase_services.download_file_to_temp(short_doc['short_video_saliency'])

        if 'cuts' not in short_doc:
            update_message("Determining boundaries...")
            # Assuming determine_boundaries has been updated to use request_id
            determine_boundaries(request_id)

        short_doc = firebase_services.get_document("shorts", short_id)
        cuts = short_doc['cuts']
        update_message("Processing video cuts...")
        update_progress(30)

        total_frames = short_doc['total_frame_count']
        update_message("Generating bounding boxes")
        update_temp_progress = lambda x: update_progress(30 + 40 * (x/100))

        all_bounding_boxes = bounding_box_generator.generate_bounding_boxes(short_video_saliency, update_temp_progress, skip_frames=2)

        update_message("Interpolating and smoothing bounding boxes within camera cuts")
        update_progress(70)

        interpolated_boxes = {
            "standard_tiktok": [],
            "two_boxes": [],
            "reaction_box": []
        }

        for i, cut_end in enumerate(cuts + [total_frames]):
            cut_start = cuts[i-1] if i > 0 else 0
            for box_type in interpolated_boxes.keys():
                segment_boxes = all_bounding_boxes[box_type][cut_start:cut_end]
                smooth_segment = smooth_bounding_boxes(segment_boxes, window_size=max(int(len(segment_boxes) / 5), 1))
                interpolated_boxes[box_type].extend(smooth_segment)

        update_message("Finalizing bounding boxes")
        update_progress(90)

        update_progress(100)
        update_message("Successfully found bounding boxes")

        firebase_services.update_document(
            "shorts",
            short_id,
            {
                "bounding_boxes": json.dumps(interpolated_boxes),
                "box_type": ['standard_tiktok' for _ in range(len(interpolated_boxes['standard_tiktok']))],
                "pending_operation": False,
            }
        )

        if auto_generate:
            firebase_services.create_short_request(
                "v1/generate-a-roll",
                short_id,
                request_doc.get('uid', 'SERVER REQUEST')
            )

        return jsonify({
            "status": "success",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
                "bounding_boxes": json.dumps(interpolated_boxes),
                "box_type": ['standard_tiktok' for _ in range(len(interpolated_boxes['standard_tiktok']))]
            },
            "message": "Successfully found bounding boxes"
        }), 200

    except Exception as e:
        error_message = f"Failed to find bounding boxes: {str(e)}"
        update_message(error_message)
        firebase_services.update_document("shorts", short_id, {
            "pending_operation": False,
            "auto_generate": False
        })
        return jsonify({
            "status": "error",
            "data": {"request_id": request_id, "short_id": short_id, "error": str(e)},
            "message": error_message
        }), 500


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


@spacial_segmentation.route("/v1/create-cropped-video/<request_id>", methods=['GET'])
def create_cropped_video(request_id):
    firebase_service = FirebaseService()
    try:
        request_doc = firebase_service.get_document("requests", request_id)
        if not request_doc:
            return jsonify({"status": "error", "message": "Request not found"}), 404

        short_id = request_doc.get('shortId')
        if not short_id:
            return jsonify({"status": "error", "message": "Short ID not found in request"}), 400

        short_doc = firebase_service.get_document("shorts", short_id)
        if not short_doc:
            return jsonify({"status": "error", "message": "Short document not found"}), 404

        text_service = AddTextToVideoService()
        video_audio_merger = VideoAudioMerger()

        def update_progress(progress):
            firebase_service.update_document("shorts", short_id, {"update_progress": progress})
            firebase_service.update_document("requests", request_id, {"progress": progress})

        def update_message(message):
            firebase_service.update_document("shorts", short_id, {
                "progress_message": message,
                "last_updated": firestore.firestore.SERVER_TIMESTAMP
            })
            firebase_service.update_message(request_id, message)

        update_temp_progress = lambda x, start, length: update_progress(start + (length * (x / 100)))

        auto_generate = short_doc.get('auto_generate', False)

        update_message("Retrieved the document")
        firebase_service.update_document("shorts", short_id, {"pending_operation": True})

        update_progress(20)
        if "short_b_roll" not in short_doc and "short_a_roll" not in short_doc:
            update_message("B Roll Does Not Exist!")
            firebase_service.update_document("shorts", short_id, {"pending_operation": False})
            return jsonify({
                "status": "error",
                "data": {
                    "request_id": request_id,
                    "short_id": short_id,
                    "error": "No b roll combined found"
                },
                "message": "Failed to preview video"
            }), 400

        update_message("Accessed the short document")
        clipped_footage = short_doc.get("short_b_roll", short_doc.get("short_a_roll", ""))
        update_message("Download the clipped video")
        output_path = firebase_service.download_file_to_temp(clipped_footage)
        update_progress(30)

        # Get video properties
        COLOUR = (13, 255, 0)
        SHADOW_COLOUR = (192, 255, 189)
        LOGO = "ViraNova"

        if 'short_title_top' in short_doc:
            update_message("Added top text")
            update_progress(65)
            output_path = text_service.add_text_centered(output_path, short_doc['short_title_top'].upper(), 1.7,
                                                         thickness='Bold', color=(255, 255, 255),
                                                         shadow_color=(0, 0, 0),
                                                         shadow_offset=(1, 1), outline=True, outline_color=(0, 0, 0),
                                                         outline_thickness=1, offset=(0, 0.15))

        if 'short_title_bottom' in short_doc:
            update_message("Added bottom text")
            update_progress(70)
            output_path = text_service.add_text_centered(output_path, short_doc['short_title_bottom'].upper(), 1.7,
                                                         thickness='Bold',
                                                         color=COLOUR, shadow_color=SHADOW_COLOUR,
                                                         shadow_offset=(1, 1), outline=False, outline_color=(0, 0, 0),
                                                         outline_thickness=1, offset=(0, 0.18))

        output_path = text_service.add_text_centered(output_path, LOGO, 1,
                                                     thickness='Bold',
                                                     color=COLOUR, shadow_color=(0, 0, 0),
                                                     shadow_offset=(1, 1), outline=False, outline_color=(0, 0, 0),
                                                     outline_thickness=1, offset=(0, 0.1))

        add_transcript = True
        if add_transcript:
            segment_document = firebase_service.get_document('topical_segments', short_doc['segment_id'])

            try:
                segment_document_words = parse_segment_words(segment_document)
            except ValueError as e:
                error_message = f"Error parsing segment words: {str(e)}"
                update_message(error_message)
                firebase_service.update_document("shorts", short_id, {"pending_operation": False})
                return jsonify({
                    "status": "error",
                    "data": {"request_id": request_id, "short_id": short_id, "error": error_message},
                    "message": "Failed to parse segment words"
                }), 400

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
                update_temp_progress(index / len(adjusted_words_to_handle) * 100, 75, 15)

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
        generate_test_audio_for_short(request_id)  # Assuming this function has been updated to use request_id
        update_message("Adding audio now")
        short_doc = firebase_service.get_document("shorts", short_id)

        audio_path = firebase_service.download_file_to_temp(short_doc['temp_audio_file'],
                                                            short_doc['temp_audio_file'].split(".")[-1])
        output_path = add_audio_to_video(output_path, audio_path)

        if "background_audio" in short_doc:
            background_audio = firebase_service.get_document("stock-audio", short_doc['background_audio'])
            temp_audio_location = firebase_service.download_file_to_temp(background_audio['storageLocation'])
            output_path = video_audio_merger.merge_audio_to_video(output_path, temp_audio_location,
                                                                  short_doc['background_percentage'])

        # Create an output path
        update_message("Added output path to short location")
        destination_blob_name = "finished-short/" + short_id + "-" + "".join(clipped_footage.split("/")[1:])
        firebase_service.upload_file_from_temp(output_path, destination_blob_name)

        firebase_service.update_document("shorts", short_id, {"finished_short_location": destination_blob_name,
                                                              "finished_short_fps": short_doc['fps']})

        update_message("Finished Video!")
        firebase_service.update_document("shorts", short_id, {
            "pending_operation": False,
            "auto_generate": False
        })

        if "uid" in short_doc:
            email = get_user_email(short_doc['uid'])
            email_service = EmailService()
            email_service.send_video_ready_notification(email, short_doc['short_id'], '')

        return jsonify({
            "status": "success",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
                "finished_short_location": destination_blob_name,
                "finished_short_fps": short_doc['fps']
            },
            "message": "Successfully previewed final video"
        }), 200

    except Exception as e:
        error_message = f"Failed to preview video: {str(e)}"
        update_message(error_message)
        firebase_service.update_document("shorts", short_id, {
            "pending_operation": False,
            "auto_generate": False
        })
        return jsonify({
            "status": "error",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
                "error": str(e)
            },
            "message": error_message
        }), 500
