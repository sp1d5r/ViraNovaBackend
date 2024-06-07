import tempfile
from flask import Blueprint
from services.firebase import FirebaseService
from services.saliency_detection.segmentation_optic_flow_saliency_detection import OpticFlowSegmentedSaliencyDetector
from datetime import datetime

short_saliency = Blueprint("get_saliency_for_short", __name__)

@short_saliency.route("/get_saliency_for_short/<short_id>")
def get_saliency_for_short(short_id):
    firebase_service = FirebaseService()
    saliency_service = OpticFlowSegmentedSaliencyDetector()

    short_document = firebase_service.get_document("shorts", short_id)
    update_progress = lambda x: firebase_service.update_document("shorts", short_id, {"update_progress": x})
    update_message = lambda x: firebase_service.update_document("shorts", short_id, {"progress_message": x, "last_updated": datetime.now()})
    firebase_service.update_document("shorts", short_id, {"pending_operation": True})

    short_video_path = short_document['short_clipped_video']

    if short_video_path is None:
        firebase_service.update_document("shorts", short_id, {"pending_operation": False})
        return "No short video path found", 404

    update_message("Loading video into temp locations")
    update_progress(20)
    temp_location = firebase_service.download_file_to_temp(short_video_path)
    _, output_path = tempfile.mkstemp(suffix='.mp4')

    update_message("Calculating the saliency")
    update_progress_saliency = lambda x: update_progress(30 + 50 * (x / 100))
    saliency_service.generate_video_saliency(temp_location, update_progress_saliency, short_id=short_id, skip_frames=5, save_path=output_path)

    update_message("Uploading to firebase")
    update_progress(90)
    destination_blob_name = "short-video-saliency/" + short_id + "-" + "".join(short_video_path.split("/")[1:])
    firebase_service.upload_file_from_temp(output_path, destination_blob_name)

    update_message("Updating short document")
    firebase_service.update_document("shorts", short_id, {"pending_operation": False})
    firebase_service.update_document("shorts", short_id, {"short_video_saliency": destination_blob_name})

    return "Completed Saliency Calculation"
