from serverless_backend.services.bounding_box_services import smooth_bounding_boxes
from serverless_backend.services.bounding_box_generator.bounding_boxes import BoundingBoxGenerator
from serverless_backend.services.verify_video_document import parse_and_verify_short
from serverless_backend.services.add_text_to_video_service import AddTextToVideoService
from serverless_backend.services.video_audio_merger import VideoAudioMerger
from serverless_backend.services.email.brevo_email_service import EmailService
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.video_analyser.video_analyser import VideoAnalyser
from firebase_admin import auth, firestore
from flask import Blueprint, jsonify

from serverless_backend.services.video_merger import combine_videos


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
import json

def add_audio_to_video(video_path, audio_path):
    output_path = video_path.rsplit('.', 1)[0] + '_with_audio.mp4'

    command = [
        'ffmpeg',
        '-i', video_path,
        '-i', audio_path,
        '-c:v', 'libx264',  # Explicitly use libx264
        '-preset', 'medium',
        '-crf', '23',
        '-c:a', 'aac',
        '-strict', 'experimental',
        '-movflags', '+faststart',  # Optimize for web playback
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
        input_path = firebase_service.download_file_to_temp(clipped_footage)
        update_progress(30)

        # Default branding settings
        PRIMARY_COLOUR = (0, 255, 0)  # Green
        SECONDARY_COLOUR = (192, 255, 189)  # Light green
        LOGO = "ViraNova"

        # Get user document and update branding if available
        user_id = request_doc.get('uid')
        if user_id:
            user_doc = firebase_service.get_document("users", user_id)
            if user_doc:
                if 'channelName' in user_doc.keys():
                    LOGO = user_doc['channelName']
                    # If colors are coming from hex strings, convert them correctly
                if 'primaryColor' in user_doc.keys():
                    hex_color = user_doc['primaryColor'].lstrip('#')
                    PRIMARY_COLOUR = tuple(int(hex_color[i:i + 2], 16) for i in (4, 2, 0))  # Convert to BGR

                if 'secondaryColor' in user_doc.keys():
                    hex_color = user_doc['secondaryColor'].lstrip('#')
                    SECONDARY_COLOUR = tuple(int(hex_color[i:i + 2], 16) for i in (4, 2, 0))  # Convert to BGR

        # Prepare text additions
        text_additions = []
        if 'short_title_top' in short_doc.keys():
            text_additions.append({
                'text': short_doc['short_title_top'].upper(),
                'font_scale': 2,
                'thickness': 'Bold',
                'color': (255, 255, 255),
                'static': True,
                'shadow_color': (0, 0, 0),
                'shadow_offset': (1, 1),
                'outline': True,
                'outline_color': (0, 0, 0),
                'outline_thickness': 3,
                'offset': (0, 0.15)
            })

        if 'short_title_bottom' in short_doc:
            text_additions.append({
                'text': short_doc['short_title_bottom'].upper(),
                'font_scale': 2,
                'thickness': 'Bold',
                'color': PRIMARY_COLOUR,
                'static': True,
                'shadow_color': (0, 0, 0),
                'shadow_offset': (1, 1),
                'outline': True,
                'outline_color': SECONDARY_COLOUR,
                'outline_thickness': 2,
                'offset': (0, 0.17)
            })

        text_additions.append({
            'text': LOGO,
            'font_scale': 1.7,
            'thickness': 'Bold',
            'color': PRIMARY_COLOUR,
            'static': True,
            'shadow_color': (0, 0, 0),
            'shadow_offset': (1, 1),
            'outline': True,
            'outline_color': (0, 0, 0),
            'outline_thickness': 2,
            'offset': (0, 0.1)
        })

        # Add transcript if needed
        if 'lines' in short_doc:
            lines = short_doc['lines']
            update_message("Processing transcript lines")
            update_progress(50)

            texts = []
            start_times = []
            end_times = []

            for line in lines:
                text = " ".join([word['word'] for word in line['words']])
                texts.append(text.lower())  # Changed to lowercase as per your test script
                start_times.append(line['start_time'])
                end_times.append(line['end_time'])

                update_message(f"Added line: {text}")
                update_temp_progress(lines.index(line) / len(lines) * 100, 75, 15)

            text_additions.append({
                'type': 'transcript',
                'texts': texts,
                'start_times': start_times,
                'end_times': end_times,
                'font_scale': 3,  # Increased as per your test script
                'thickness': 'Bold',
                'color': (255, 255, 255),
                'shadow_color': (0, 0, 0),
                'shadow_offset': (1, 1),
                'outline': True,
                'outline_color': (0, 0, 0),
                'outline_thickness': 4,  # Increased as per your test script
                'offset': (0, 0.05)  # Changed as per your test script
            })

        # Process video with all text additions in one pass
        update_message("Adding text to video")
        output_path = text_service.process_video_with_text(input_path, text_additions)
        update_progress(70)

        update_message("Adding audio now")
        short_doc = firebase_service.get_document("shorts", short_id)

        audio_path = firebase_service.download_file_to_temp(short_doc['temp_audio_file'],
                                                            short_doc['temp_audio_file'].split(".")[-1])
        output_path = add_audio_to_video(output_path, audio_path)

        if "background_audio" in short_doc.keys():
            background_audio = firebase_service.get_document("stock-audio", short_doc['background_audio'])
            temp_audio_location = firebase_service.download_file_to_temp(background_audio['storageLocation'])
            output_path = video_audio_merger.merge_audio_to_video(output_path, temp_audio_location,
                                                                  short_doc['background_percentage'])

        if "intro_video_path" in short_doc.keys():
            update_message("Adding intro video")
            update_progress(80)
            intro_video_path = firebase_service.download_file_to_temp(short_doc['intro_video_path'])
            output_path = combine_videos(intro_video_path, output_path)

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
            email_service.send_video_ready_notification(email, short_id, '')

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
