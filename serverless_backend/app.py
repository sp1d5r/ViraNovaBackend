import awsgi
from firebase_admin import firestore

from serverless_backend.routes.generate_image import generate_images
from serverless_backend.routes.generate_short_ideas import generate_short_ideas
from serverless_backend.routes.deprecated.get_random_video import get_random_video
from serverless_backend.routes.deprecated.get_segmentation_masks import get_segmentation_mask
from serverless_backend.routes.deprecated.get_shorts_and_segments import get_shorts_and_segments
from serverless_backend.routes.get_tiktok_analytics import tiktok_analytics
from serverless_backend.routes.query.query_catalog import query_catalog
from serverless_backend.routes.spacial_segmentation import spacial_segmentation
from serverless_backend.routes.summarise_segments import summarise_segments
from serverless_backend.routes.create_short_video import create_short_video
from serverless_backend.routes.transcribe_and_diarize_audio import transcribe_and_diarize_audio
from serverless_backend.routes.split_video_and_audio import split_video_and_audio
from serverless_backend.routes.edit_transcript import edit_transcript
from serverless_backend.routes.topical_segmentation import topical_segmentation
from serverless_backend.routes.get_saliency_for_short import short_saliency
from serverless_backend.routes.generate_test_audio import generate_test_audio
from serverless_backend.routes.extract_segment_from_video import extract_segment_from_video
from serverless_backend.routes.add_channel import add_channel
from serverless_backend.routes.wyr.generate_video_ideas import generate_video_ideas
from serverless_backend.routes.wyr.new_wyr_video import new_wyr_video
from serverless_backend.routes.youtube_webhook import youtube_webhook
from serverless_backend.routes.generate_a_roll import generate_a_roll
from serverless_backend.routes.generate_b_roll import generate_b_roll
from serverless_backend.routes.youtube_link import youtube_link
from serverless_backend.routes.transcribe_video import transcribe
from serverless_backend.routes.edit_transcript_v2 import edit_transcript_v2
from serverless_backend.routes.generate_intro import generate_intro
from serverless_backend.routes.generate_intro_video import generate_intro_video
from serverless_backend.routes.manual_override_transcript import manual_override_transcript
from flask_cors import CORS
from flask import Flask, request, jsonify, g
import os
from serverless_backend.services.firebase import FirebaseService
import jwt
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

origins = [
    "http://localhost:3000/segmentation",
    "https://master.d2gor5eji1mb54.amplifyapp.com",
    "http://localhost:5000",
    "http://localhost:8000",
    "http://localhost:3000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:5000"
    "http://127.0.0.1:3000"
]

CORS(app, resources={r"/*": {"origins": origins}})

# Registering Routes
app.register_blueprint(split_video_and_audio)
app.register_blueprint(transcribe_and_diarize_audio)
app.register_blueprint(topical_segmentation)
app.register_blueprint(summarise_segments)
app.register_blueprint(get_random_video)
app.register_blueprint(get_segmentation_mask)
app.register_blueprint(get_shorts_and_segments)
app.register_blueprint(generate_short_ideas)
app.register_blueprint(create_short_video)
app.register_blueprint(spacial_segmentation)
app.register_blueprint(youtube_link)
app.register_blueprint(edit_transcript)
app.register_blueprint(edit_transcript_v2)
app.register_blueprint(short_saliency)
app.register_blueprint(generate_test_audio)
app.register_blueprint(extract_segment_from_video)
app.register_blueprint(tiktok_analytics)
app.register_blueprint(add_channel)
app.register_blueprint(youtube_webhook)
app.register_blueprint(generate_a_roll)
app.register_blueprint(generate_b_roll)
app.register_blueprint(transcribe)
app.register_blueprint(generate_intro)
app.register_blueprint(generate_intro_video)
app.register_blueprint(manual_override_transcript)
app.register_blueprint(generate_images)
app.register_blueprint(new_wyr_video)
app.register_blueprint(query_catalog)

# Would You Rather
app.register_blueprint(generate_video_ideas)

# App Before/After Hooks
SERVER_STATUS_COLUMN_NAME = "backend_status"
SERVER_STATUS_PENDING = "Pending"
SERVER_STATUS_COMPLETE = "Completed"
SERVER_STATUS_PROCESSING = "Processing"

SECRET_KEY = os.getenv("SECRET_KEY")

def verify_jwt(token, secret_key):
    try:
        decoded = jwt.decode(token, secret_key, algorithms=['HS256'])
        return decoded
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


@app.before_request
def check_status():
    if request.path == '/youtube-webhook':
        return None

    # Verify request beforehand
    auth_header = request.headers.get('X-Auth-Token', None)
    if auth_header:
        parts = auth_header.split()
        if parts[0].lower() != 'bearer' or len(parts) == 1 or len(parts) > 2:
            print('Invalid Authorization header format')
            return jsonify({'message': 'Invalid Authorization header format'}), 401

        token = parts[1]
        decoded = verify_jwt(token, SECRET_KEY)
        if decoded is None:
            print('Invalid or expired token')
            return jsonify({'message': 'Invalid or expired token'}), 401
    else:
        print('Authorization header missing')
        return jsonify({'message': 'Authorization header missing'}), 401

    video_id = None
    short_id = None
    segment_id = None
    request_id = None

    # Get video / segment / short
    if request.view_args:
        video_id = request.view_args.get('video_id')
        short_id = request.view_args.get('short_id')
        segment_id = request.view_args.get("segment_id")
        request_id = request.view_args.get('request_id')

    firebase_service = FirebaseService()

    # For Video Endpoints
    if video_id:
        video_document = firebase_service.get_document("videos", video_id)
        status = video_document.get(SERVER_STATUS_COLUMN_NAME, SERVER_STATUS_PENDING)
        if status == SERVER_STATUS_PROCESSING:
            return jsonify({'message': f'Task already {status.lower()}. Please wait or check the result.'}), 400
        else:
            # Set the status to 'Processing' and save it in the request context
            firebase_service.update_document('videos', video_id, {SERVER_STATUS_COLUMN_NAME: SERVER_STATUS_PROCESSING})
            g.video_document = video_document

    # For Segment Endpoints
    if segment_id:
        segment_document = firebase_service.get_document("topical_segments", segment_id)
        status = segment_document.get(SERVER_STATUS_COLUMN_NAME, SERVER_STATUS_PENDING)
        if status == SERVER_STATUS_PROCESSING:
            return jsonify({'message': f'Task already {status.lower()}. Please wait or check the result.'}), 400
        else:
            # Set the status to 'Processing' and save it in the request context
            firebase_service.update_document('topical_segments', segment_id, {SERVER_STATUS_COLUMN_NAME: SERVER_STATUS_PROCESSING})
            g.segment_document = segment_document

    # For Short Endpoints
    if short_id:
        short_document = firebase_service.get_document("shorts", short_id)
        status = short_document.get(SERVER_STATUS_COLUMN_NAME, SERVER_STATUS_PENDING)
        print("Status:", status)
        if status == SERVER_STATUS_PROCESSING:
            return jsonify({'message': f'Task already {status.lower()}. Please wait or check the result.'}), 400
        else:
            # Set the status to 'Processing' and save it in the request context
            firebase_service.update_document('shorts', short_id, {SERVER_STATUS_COLUMN_NAME: SERVER_STATUS_PROCESSING})
            g.short_document = short_document

    # for Request Endpoints
    if request_id:
        request_doc = firebase_service.get_document("requests", request_id)
        if not request_doc:
            return jsonify({'message': 'Request not found'}), 404

        if 'serverStartedTimestamp' in request_doc:
            firebase_service.update_message(request_id, 'Request is already being processed')
            return jsonify({'message': 'Request is already being processed'}), 400

        firebase_service.update_document('requests', request_id, {
            'serverStartedTimestamp': firestore.firestore.SERVER_TIMESTAMP
        })

        if "shortId" in request_doc.keys():
            short_id = request_doc['shortId']

            short_document = firebase_service.get_document("shorts", short_id)
            status = short_document.get(SERVER_STATUS_COLUMN_NAME, SERVER_STATUS_PENDING)
            print("Status:", status)
            if status == SERVER_STATUS_PROCESSING:
                firebase_service.update_message(request_id,  f'Task already {status.lower()}. Please wait or check the result.')
                return jsonify({'message': f'Task already {status.lower()}. Please wait or check the result.'}), 400
            else:
                # Set the status to 'Processing' and save it in the request context
                firebase_service.update_document('shorts', short_id, {SERVER_STATUS_COLUMN_NAME: SERVER_STATUS_PROCESSING})
                g.short_document = short_document

        g.request_document = request_doc
        g.request_id = request_id


@app.after_request
def update_status(response):
    if request.view_args is None:
        return response

    print("RESPONSE STATUS: ", response.status)


    try:
        response_data = response.get_json()
        print("RESPONSE DATA: ", response_data)
    except Exception as e:
        print("Failed to get JSON response:", str(e))

    # Get video / segment / short
    video_id = request.view_args.get('video_id')
    short_id = request.view_args.get('short_id')
    segment_id = request.view_args.get("segment_id")
    request_id = request.view_args.get("request_id")

    firebase_service = FirebaseService()

    is_successful = 200 <= response.status_code < 300

    if video_id:

        if is_successful:
            firebase_service.update_document("videos", video_id, {SERVER_STATUS_COLUMN_NAME: SERVER_STATUS_COMPLETE})
        else:

            firebase_service.update_document("videos", video_id, {
                SERVER_STATUS_COLUMN_NAME: SERVER_STATUS_COMPLETE,
                "error": True,
                "errorMessage": "Failed to process video... Try again?"
            })


    if segment_id:
        firebase_service.update_document("topical_segments", segment_id,
                                         {SERVER_STATUS_COLUMN_NAME: SERVER_STATUS_COMPLETE})
    if short_id:
        firebase_service.update_document("shorts", short_id,
                                         {SERVER_STATUS_COLUMN_NAME: SERVER_STATUS_COMPLETE, "pending_operation": False})
    if request_id:
        request_doc = firebase_service.get_document("requests", request_id)
        if request_doc:
            short_id = request_doc.get('shortId')
            user_id = request_doc.get('uid')
            credit_cost = request_doc.get('creditCost', 0)

            # Update request document
            if is_successful:
                firebase_service.update_document('requests', request_id, {
                    'serverCompletedTimestamp': firestore.firestore.SERVER_TIMESTAMP,
                    'status': 'completed',
                    'creditCost': credit_cost,
                    'progress': 100,
                })
            else:
                firebase_service.update_document('requests', request_id, {
                    'serverCompletedTimestamp': firestore.firestore.SERVER_TIMESTAMP,
                    'status': 'failed',
                    'creditCost': 0,
                    'progress': 100,
                })

            # Update short document
            if short_id:
                if is_successful:
                    firebase_service.update_document("shorts", short_id, {
                        SERVER_STATUS_COLUMN_NAME: SERVER_STATUS_COMPLETE,
                        "pending_operation": False
                    })
                else:
                    firebase_service.update_document("shorts", short_id, {
                        SERVER_STATUS_COLUMN_NAME: SERVER_STATUS_COMPLETE,
                        "pending_operation": False,
                        "auto_generate": False,
                    })

            # Deduct credits from user
            if user_id and credit_cost > 0:
                try:
                    user_doc = firebase_service.get_document("users", user_id)
                    if user_doc and 'credits' in user_doc and is_successful:
                        current_credits = user_doc['credits'].get('current', 0)
                        new_credit_balance = max(current_credits - credit_cost, 0)
                        firebase_service.update_document("users", user_id, {
                            'credits.current': new_credit_balance
                        })
                        print(f"Credits deducted. New balance for user {user_id}: {new_credit_balance}")
                except Exception as e:
                    print(f"Error deducting credits for user {user_id}: {str(e)}")

    return response



@app.route("/")
def main_route():
    return "Viranova Backend"

def list_routes(app):
    output = []
    for rule in app.url_map.iter_rules():
        methods = ','.join(rule.methods)
        url = rule.rule
        output.append((url, methods))
    return output


# # Lambda handler
def lambda_handler(event, context):
    print("The event: ", event)
    print("The context: ", context)
    return awsgi.response(app, event, context)

if __name__ == '__main__':
    print(list_routes(app))
    app.run(host='0.0.0.0', port=5000, debug=False)
