import json
from flask import Blueprint, jsonify
from firebase_admin import firestore
from datetime import datetime
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip, vfx
import numpy as np

from serverless_backend.routes.spacial_segmentation import add_audio_to_video
from serverless_backend.services.add_text_to_video_service import AddTextToVideoService
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.verify_video_document import parse_and_verify_short
import tempfile
import os
import time

generate_intro_video = Blueprint("generate_intro_video", __name__)


def generate_intro_sequence(input_video_path, input_audio_path, short_doc, user_doc, text_service):
    print(f"Starting video processing. Input video: {input_video_path}, Input audio: {input_audio_path}")

    # Load the video and audio
    video = VideoFileClip(input_video_path)
    audio = AudioFileClip(input_audio_path)

    # Get the duration of the intro audio
    intro_duration = audio.duration
    print(f"Audio duration: {intro_duration} seconds")

    # Trim the video to match the audio duration
    video = video.subclip(0, intro_duration)
    print(f"Video trimmed to {intro_duration} seconds")

    # Get the first bounding box
    bounding_boxes = json.loads(short_doc.get('bounding_boxes', '{}'))
    first_box = bounding_boxes.get('standard_tiktok', [[]])[0]
    print(f"First bounding box: {first_box}")

    # Crop the video to the bounding box
    x, y, w, h = first_box
    cropped_video = video.crop(x1=x, y1=y, width=w, height=h)
    print(f"Video cropped to bounding box: {w}x{h}")

    # Resize the video to 1080x1920
    resized_video = cropped_video.resize(height=1920)
    # If the width is less than 1080, pad it
    if resized_video.w < 1080:
        pad_width = (1080 - resized_video.w) // 2
        final_video = CompositeVideoClip([resized_video.set_position(("center", "center"))], size=(1080, 1920))
    else:
        final_video = resized_video.resize(width=1080)
    print(f"Video resized to 1080x1920")

    # Set the audio for the final clip
    final_video = final_video.set_audio(audio)

    # Default branding settings
    PRIMARY_COLOUR = (0, 255, 0)  # Green
    SECONDARY_COLOUR = (192, 255, 189)  # Light green
    LOGO = "ViraNova"


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

    # Prepare text additions for AddTextToVideoService
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

    # Write the final clip to a temporary file
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False, dir="/tmp") as temp_output_path:
        temp_video_path = temp_output_path.name

    try:
        final_video.write_videofile(temp_video_path, codec='libx264', audio_codec='aac', fps=30, temp_audiofile="/tmp/output_file.m4a")
        print("Video writing completed successfully")
    except Exception as e:
        print(f"Error writing video file: {str(e)}")
        raise

    # Wait for a short time to ensure file system updates are complete
    time.sleep(1)

    # Verify the video file
    max_attempts = 5
    for attempt in range(max_attempts):
        if os.path.exists(temp_video_path):
            file_size = os.path.getsize(temp_video_path)
            print(f"Attempt {attempt + 1}: File exists. Size: {file_size} bytes")
            if file_size > 0:
                break
        else:
            print(f"Attempt {attempt + 1}: File does not exist")

        if attempt < max_attempts - 1:
            print("Waiting before next attempt...")
            time.sleep(1)
    else:
        raise FileNotFoundError(
            f"Video file was not created or is empty after {max_attempts} attempts: {temp_video_path}")

    print(f"Video file created successfully. Final size: {os.path.getsize(temp_video_path)} bytes")

    # Verify the video file can be opened
    try:
        with VideoFileClip(temp_video_path) as check_clip:
            print(f"Video duration: {check_clip.duration} seconds")
    except Exception as e:
        print(f"Error opening video file: {str(e)}")
        raise

    # Use AddTextToVideoService to add text to the intro video
    try:
        intro_with_text_path = text_service.process_video_with_text(temp_video_path, text_additions)
        print(f"Text added to video. Final path: {intro_with_text_path}")
    except Exception as e:
        print(f"Error adding text to video: {str(e)}")
        raise

    output_path = add_audio_to_video(intro_with_text_path, input_audio_path)

    return output_path


@generate_intro_video.route("/v1/generate-intro-video/<request_id>", methods=['GET'])
def generate_intro_info(request_id):
    firebase_service = FirebaseService()

    try:
        request_doc = firebase_service.get_document("requests", request_id)
        if not request_doc:
            return jsonify({"status": "error", "message": "Request not found"}), 404

        short_id = request_doc.get('shortId')
        if not short_id:
            return jsonify({"status": "error", "message": "Short ID not found in request"}), 400

        short_document = firebase_service.get_document("shorts", short_id)
        if not short_document:
            return jsonify({"status": "error", "message": "Short document not found"}), 404

        # Update request log to indicate process initiation
        firebase_service.update_document("requests", request_id, {
            "logs": firestore.firestore.ArrayUnion([{
                "message": "Contextual Intro Generated",
                "timestamp": datetime.now()
            }])
        })

        is_valid_document, error_message = parse_and_verify_short(short_document)
        if not is_valid_document:
            firebase_service.update_document("shorts", short_id, {
                "logs": firestore.firestore.ArrayUnion([{
                    "time": datetime.now(),
                    "message": f"Invalid short document: {error_message}",
                    "type": "error"
                }])
            })
            firebase_service.update_message(request_id, "Contextual Intro Failed: Invalid short document")
            return jsonify({
                "status": "error",
                "data": {
                    "request_id": request_id,
                    "short_id": short_id,
                    "error": error_message
                },
                "message": "Invalid short document"
            }), 400

        auto_generate = short_document.get('auto_generate', False)

        firebase_service.update_document("shorts", short_id, {"pending_operation": True})

        def update_progress(progress):
            firebase_service.update_document('shorts', short_id, {'update_progress': progress})

        def update_message(message):
            firebase_service.update_document('shorts', short_id, {
                'progress_message': message,
                'last_updated': firestore.firestore.SERVER_TIMESTAMP
            })
            firebase_service.update_message(request_id, message)

        text_service = AddTextToVideoService()

        user_id = request_doc.get('uid')
        user_doc = None
        if user_id:
            user_doc = firebase_service.get_document("users", user_id)

        if 'intro_audio_path' in short_document.keys() and 'short_clipped_video' in short_document.keys():
            print("Generating intro video...")
            input_audio_file = firebase_service.download_file_to_temp(short_document['intro_audio_path'])
            input_path = firebase_service.download_file_to_temp(short_document['short_clipped_video'])
            output_video_path = generate_intro_sequence(input_path, input_audio_file, short_document, user_doc, text_service)

            output_blob_location = "intro-video/" + short_id + "/" + short_id + "-intro.mp4"
            firebase_service.upload_file_from_temp(output_video_path, output_blob_location)

            # Update the short document with the intro video blob path
            firebase_service.update_document("shorts", short_id, {
                "intro_video_path": output_blob_location
            })

        update_message("Intro video generated successfully")
        update_progress(100)

        if auto_generate:
            firebase_service.create_short_request(
                "v1/create-cropped-video",
                short_id,
                request_doc.get('uid', 'SERVER REQUEST')
            )

        return jsonify({
            "status": "success",
            "data": {
                "request_id": request_id,
                "short_id": short_id,
            },
            "message": "Successfully generated intro audio."
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "data": {
                "request_id": request_id,
                "error": str(e)
            },
            "message": "Failed to process generated intro audio"
        }), 500



