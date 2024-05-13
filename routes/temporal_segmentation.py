import ast

from flask import Blueprint, jsonify
from services.firebase import FirebaseService
from services.langchain_chains.crop_segment import requires_cropping_chain, delete_operation_chain
from services.langchain_chains.idea_generator_chain import idea_generator_chain
from services.verify_video_document import parse_and_verify_short, parse_and_verify_video, parse_and_verify_segment
from datetime import datetime
from pydub import AudioSegment
from io import BytesIO

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

    # Modify the list to include the deletion placeholder and remove other words in the range
    new_words_with_index = []
    for position, (index, word) in enumerate(words_with_index):
        if position == start_position:
            # Add a placeholder text indicating a deletion from start_index to end_index
            new_words_with_index.append((index, f"..."))
        elif index < start_index or index > end_index:
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
        MAX_ERROR_LIMIT = short_document["error_count"]

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

                does_transcript_require_cropping = requires_cropping_chain.invoke(
                    {"transcript": " ".join([f"{i[1]}" for i in words_with_index]), "short_idea": short_idea})

                update_logs({
                    "time": datetime.now(),
                    "title": "Chain Operation",
                    "message": f"CHAIN: Does the transcript need to be cropped = {does_transcript_require_cropping.requires_cropping}",
                    "type": "message"
                })

                update_logs({
                    "time": datetime.now(),
                    "message": f"CHAIN: Explanation: {does_transcript_require_cropping.explanation}",
                    "type": "message"
                })

                if does_transcript_require_cropping.requires_cropping:
                    update_logs({
                        "time": datetime.now(),
                        "message": "CHAIN: Determining where to crop...",
                        "type": "message"
                    })

                    transcript_delete_operation = delete_operation_chain.invoke(
                        {"transcript": " ".join([f"({i[0]}) {i[1]}" for i in words_with_index]),
                         "short_idea": short_idea})

                    update_logs({
                        "time": datetime.now(),
                        "message":f"CHAIN: Deleting between ({transcript_delete_operation.start_index} - {transcript_delete_operation.end_index}). Explanation: {transcript_delete_operation.explanation}",
                        "type": "delete",
                        "start_index": transcript_delete_operation.start_index,
                        "end_index": transcript_delete_operation.end_index
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

        return "Completed Segment Idea Extraction", 200
    else:
        return error_message, 404



def handle_operations_from_logs(logs, words):
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

