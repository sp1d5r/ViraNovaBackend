import ast
import uuid

from flask import Blueprint
from services.firebase import FirebaseService
from services.langchain_chains.crop_segment import requires_cropping_chain, delete_operation_chain
from services.saliency_detection.segmentation_optic_flow_saliency_detection import OpticFlowSegmentedSaliencyDetector
from services.saliency_detection.segmentation_saliency_detector import SegmentedSaliencyDetector
from services.verify_video_document import parse_and_verify_short, parse_and_verify_video, parse_and_verify_segment
from datetime import datetime
from pydub import AudioSegment
import numpy as np
from io import BytesIO
import tempfile
import os
from services.video_clipper import VideoClipper


# Route Functions

def delete_operation(words_with_index, start_index, end_index):
    # Find the position in the list for the start index
    start_position = None
    for position, (index, _) in enumerate(words_with_index):
        if index == start_index:
            start_position = position
            break

    if start_position is None:
        raise ValueError("Start index not found in the current list of words.")

    # Modify the list to clearly indicate deletions
    new_words_with_index = []
    for position, (index, word) in enumerate(words_with_index):
        if start_index <= index <= end_index:
            # Replace the word with a placeholder indicating deletion
            new_words_with_index.append((-1, word))
        else:
            new_words_with_index.append((index, word))

    return new_words_with_index

# Routes
temporal_segmentation = Blueprint("temporal_segmentation", __name__)


@temporal_segmentation.route("/temporal-segmentation/<short_id>")
def perform_temporal_segmentation(short_id):
    firebase_service = FirebaseService()
    short_document = firebase_service.get_document("shorts", short_id)
    is_valid_document, error_message = parse_and_verify_short(short_document)

    logs = [{
        "time": datetime.now(),
        "message": "Beginning Editing...",
        "type": "message"
    }]

    print(short_document)

    def update_logs(log):
        logs.append(log)
        firebase_service.update_document('shorts', short_id, {'logs': logs})

    if is_valid_document:
        print("Here")
        transcript = short_document['transcript']
        transcript_words = transcript.split(" ")
        words_with_index = [(index, word) for index, word in enumerate(transcript_words)]
        short_idea = short_document['short_idea']

        error_count = 0
        MAX_ERROR_LIMIT = 5

        print(f"error_count {error_count}, max limit: {short_document}")

        while error_count < MAX_ERROR_LIMIT:
            print("Began loop!")
            try:
                update_logs({
                    "time": datetime.now(),
                    "title": "Chain Operation",
                    "message": "Checking if the transcript needs to be edited.",
                    "type": "message"
                })

                requires_cropping_uuid = uuid.uuid4()
                does_transcript_require_cropping = requires_cropping_chain.invoke(
                    {"transcript": " ".join([f"{i[1]}" for i in words_with_index if i[0] >= 0]), "short_idea": short_idea},
                    config={"run_id": requires_cropping_uuid, "metadata": {"short_id": short_id}}
                )

                update_logs({
                    "time": datetime.now(),
                    "title": "Chain Operation",
                    "message": f"CHAIN: Does the transcript need to be cropped = {does_transcript_require_cropping.requires_cropping}",
                    "type": "message",
                })

                update_logs({
                    "time": datetime.now(),
                    "message": f"CHAIN: Explanation: {does_transcript_require_cropping.explanation}",
                    "type": "message",
                    "run_id": str(requires_cropping_uuid),
                })

                if does_transcript_require_cropping.requires_cropping:
                    update_logs({
                        "time": datetime.now(),
                        "message": "CHAIN: Determining where to crop...",
                        "type": "message"
                    })

                    delete_operation_uuid = uuid.uuid4()
                    transcript_delete_operation = delete_operation_chain.invoke(
                        {"transcript": " ".join([f"({i[0]}) {i[1]}" for i in words_with_index if i[0] > 0]),
                         "short_idea": short_idea},
                        config={"run_id": delete_operation_uuid, "metadata": {"short_id": short_id}}
                    )

                    update_logs({
                        "time": datetime.now(),
                        "message":f"CHAIN: Deleting between ({transcript_delete_operation.start_index} - {transcript_delete_operation.end_index}). Explanation: {transcript_delete_operation.explanation}",
                        "type": "delete",
                        "start_index": transcript_delete_operation.start_index,
                        "end_index": transcript_delete_operation.end_index,
                        "run_id": str(transcript_delete_operation),
                    })


                    words_with_index = delete_operation(
                        words_with_index=words_with_index,
                        start_index=transcript_delete_operation.start_index,
                        end_index=transcript_delete_operation.end_index
                    )

                    update_logs({
                        "time": datetime.now(),
                        "message": "CHAIN: Deleted transcript section.",
                        "type": "message"
                    })


                    if len(words_with_index) < 70:
                        update_logs({
                            "time": datetime.now(),
                            "message": "CHAIN: Transcript has gotten met minimum word limit..",
                            "type": "success"
                        })
                        break
                else:
                    update_logs({
                        "time": datetime.now(),
                        "message": "CHAIN: Transcript editing complete!",
                        "type": "success"
                    })
                    firebase_service.update_document('shorts', short_id, {'short_status': "Clipping Complete"})
                    break
            except Exception as e:
                update_logs({
                    "time": datetime.now(),
                    "message": f"FAILED IN PIPELINE: {e}",
                    "type": "error"
                })
                error_count += 1

        if error_count >= MAX_ERROR_LIMIT:
            firebase_service.update_document('shorts', short_id, {'short_status': "Clipping Failed"})

        return "Completed Short Extraction", 200
    else:
        return error_message, 404



def handle_operations_from_logs(logs, words):
    # If update also update in spacial_segmentation
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



@temporal_segmentation.route("/generate-test-audio/<short_id>")
def generate_test_audio(short_id):
    firebase_service = FirebaseService()
    short_document = firebase_service.get_document("shorts", short_id)
    is_valid_document, error_message = parse_and_verify_short(short_document)
    if is_valid_document:
        firebase_service.update_document('shorts', short_id, {'temp_audio_file': "Loading..."})
        print("Collected Document")
        logs = short_document['logs']

        if "video_id" in short_document.keys():
            video_id = short_document['video_id']
        else:
            return "Failed - no video id in the short...", 300

        video_document = firebase_service.get_document('videos', video_id)

        is_valid_document, error_message = parse_and_verify_video(video_document)

        if not is_valid_document:
            return error_message, 404
        else:
            print("Collected video document")

        audio_file = video_document['audio_path']

        segment_document = firebase_service.get_document('topical_segments', short_document['segment_id'])

        is_valid_document, error_message = parse_and_verify_segment(segment_document)

        if not is_valid_document:
            return error_message, 404
        else:
            print("Collected semgnet document")

        segment_document_words = ast.literal_eval(segment_document['words'])
        print("Read Segment Words")
        words_to_handle = handle_operations_from_logs(logs, segment_document_words)
        print("Download Audio File to Memory")
        audio_stream = firebase_service.download_file_to_memory(audio_file)
        print("Create temporary audio file")
        audio_data = AudioSegment.from_file_using_temporary_files(audio_stream)

        combined_audio = AudioSegment.silent(duration=0)
        print("Perform operations}")
        for word in words_to_handle:
            start_time = int(word['start_time'] * 1000)
            end_time = int(word['end_time'] * 1000)
            segment = audio_data[start_time:end_time]
            combined_audio += segment

        print("Loading the bytes stream")
        byte_stream = BytesIO()
        combined_audio.export(byte_stream,
                             format='mp4')  # Use 'mp4' as the format; adjust as necessary for your audio type

        new_blob_location = 'temp-audio/' + "".join(audio_file.split("/")[1:])

        byte_stream.seek(0)
        file_bytes = byte_stream.read()
        firebase_service.upload_audio_file_from_memory(new_blob_location, file_bytes)
        print("Uploaded Result")
        firebase_service.update_document('shorts', short_id, {'temp_audio_file': new_blob_location})
        return 200, new_blob_location
    else:
        return 404, error_message


def print_file_size(file_path):
    size = os.path.getsize(file_path)
    print(f"File size of {file_path} is {size} bytes.")

@temporal_segmentation.route("/crop-segment/<segment_id>")
def crop_video_to_segment(segment_id):
    firebase_service = FirebaseService()
    video_clipper = VideoClipper()

    print("Getting Documents")
    segment_document = firebase_service.get_document("topical_segments", segment_id)
    video_document = firebase_service.get_document('videos', segment_document['video_id'])

    firebase_service.update_document("topical_segments", segment_id, {'segment_status': "Getting Segment Video"})

    words = ast.literal_eval(segment_document['words'])
    begin_cut = words[0]['start_time']
    end_cut = words[-1]['end_time']
    video_path = video_document['videoPath']

    # 1) Load in video to memory
    print("Getting video stream")
    input_path = firebase_service.download_file_to_temp(video_document['videoPath'])
    print_file_size(input_path)

    # 2) Clip video to segment
    print("Creating temporary video segment")
    _, output_path = tempfile.mkstemp(suffix='.mp4')  # Ensure it's an mp4 file
    video_clipper.clip_video(input_path, begin_cut, end_cut, output_path)

    print_file_size(output_path)

    # 3) Reupload to firebase storage
    print("Uploading to firebase")
    destination_blob_name = "segments-video/" + segment_id + "-" + "".join(video_path.split("/")[1:])
    firebase_service.upload_file_from_temp(output_path, destination_blob_name)

    # 4) Update location on short document
    firebase_service.update_document("topical_segments", segment_id, {"video_segment_location": destination_blob_name})

    # 5) Cleanup
    os.remove(input_path)
    os.remove(output_path)

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


@temporal_segmentation.route("/create-short-video/<short_id>")
def create_short_video(short_id):
    firebase_service = FirebaseService()
    video_clipper = VideoClipper()

    print("Getting Documents")
    short_document = firebase_service.get_document("shorts", short_id)
    segment_id = short_document['segment_id']
    segment_document = firebase_service.get_document("topical_segments", segment_id)

    print("Getting logs")
    # Check if the segment has a video segment location
    logs = short_document['logs']

    print("Loading Operations")
    segment_document_words = ast.literal_eval(segment_document['words'])
    start_time = segment_document_words[0]['start_time']
    print("Read Segment Words")
    words_to_handle = handle_operations_from_logs(logs, segment_document_words)
    print("Get clips start and end")

    keep_cuts = [(round(i['start_time'] - start_time, 3), round(i['end_time'] - start_time,3)) for i in words_to_handle]
    merge_cuts = merge_consecutive_cuts(keep_cuts)

    print("Loading segment video to temporary location")
    video_path = segment_document['video_segment_location']
    input_path = firebase_service.download_file_to_temp(video_path)
    print_file_size(input_path)

    # 3) Clip the short according to locations
    print("Creating temporary video segment")
    _, output_path = tempfile.mkstemp(suffix='.mp4')  # Ensure it's an mp4 file
    video_clipper.delete_segments_from_video(input_path, merge_cuts, output_path)
    print_file_size(output_path)

    print("Uploading clipped video to short location")
    destination_blob_name = "short-video/" + short_id + "-" + "".join(video_path.split("/")[1:])
    firebase_service.upload_file_from_temp(output_path, destination_blob_name)

    print("Updating short document")
    firebase_service.update_document("shorts", short_id, {"short_clipped_video": destination_blob_name})

    print("Clean up...")
    os.remove(input_path)

@temporal_segmentation.route("/get_saliency_for_short/<short_id>")
def get_saliency_for_short(short_id):
    firebase_service = FirebaseService()
    saliency_service = OpticFlowSegmentedSaliencyDetector()

    print("Getting Documents")
    short_document = firebase_service.get_document("shorts", short_id)

    short_video_path = short_document['short_clipped_video']

    if short_video_path is None:
        return 404, "No short video path found"

    print("Loading video into temp locations")
    temp_location = firebase_service.download_file_to_temp(short_video_path)
    _, output_path = tempfile.mkstemp(suffix='.mp4')

    print("Calculating the saliency")
    saliency_service.generate_video_saliency(temp_location, skip_frames=5, save_path=output_path)

    print("Uploading to firebase")
    destination_blob_name = "short-video-saliency/" + short_id + "-" + "".join(short_video_path.split("/")[1:])
    firebase_service.upload_file_from_temp(output_path, destination_blob_name)

    print("Updating short document")
    firebase_service.update_document("shorts", short_id, {"short_video_saliency": destination_blob_name})