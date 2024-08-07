from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2
import datetime
import json
from google.protobuf import duration_pb2
import jwt


def create_jwt_token(secret_key, payload):
    payload['exp'] = datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
    token = jwt.encode(payload, secret_key, algorithm='HS256')
    return token


def create_client():
    # Creates a client for the Cloud Tasks service.
    return tasks_v2.CloudTasksClient()


def create_task(client, project, queue, token, location, url):
    # Construct the fully qualified queue name.
    parent = client.queue_path(project, location, queue)

    task = {
        'http_request': {
            'http_method': tasks_v2.HttpMethod.GET,
            'url': url,
            'headers': {
                'X-Auth-Token': f'Bearer {token}'
            }
        },
    }
    # Add the task to the created queue.
    response = client.create_task(request={"parent": parent, "task": task})
    print('Task: ', task)
    print('Task created: {}'.format(response.name))


def process_video_upload(project_id,  jwt_secret, ip_address, api_route, video_id):
    # Setup your Google Cloud project details
    project = project_id  # Replace with your GCP project ID
    queue = 'viranova-preprocessing-queue'  # The name of your queue
    location = 'europe-west3'  # The location of your queue

    # The URL you want the task to request
    url = f'{ip_address}/{api_route}/{video_id}'

    payload = {
        'video_id': video_id,
        'api_route': api_route
    }

    token = create_jwt_token(jwt_secret, payload)

    # Create a Cloud Tasks client
    client = create_client()

    # Create and add a task to the queue
    create_task(client, project, queue, token, location, url)


def preprocess_video_documents(event, context):
    """
    Handle the document status change.

    :param event:
    :param context:
    :return:
    """
    import google.cloud.firestore
    import os
    from dotenv import load_dotenv

    load_dotenv()

    # Get Backend IP Address
    ip_address = os.getenv("BACKEND_SERVICE_ADDRESS")
    project_id = os.getenv("PROJECT_ID")
    jwt_secret_key = os.getenv("SECRET_KEY")

    # Setup Firestore client
    db = google.cloud.firestore.Client()

    # Get the document that triggered the function
    doc_path = context.resource
    changed_doc = db.document(doc_path).get()
    data = changed_doc.to_dict()
    document_id = doc_path.split('/')[-1]


    if data and 'status' in data and 'previousStatus' in data and data['status'] != data['previousStatus']:
        new_status = data['status']
        # Update previous status to match new status so doesn't trigger till status changed
        db.document(doc_path).update({"previousStatus": new_status})
        print(f"Document with new status: {new_status}")

        status_route_mapping = {
            "Uploaded": "v1/split-video",
            "Transcribe": "v1/transcribe",
            "Link Provided": "v1/begin-youtube-link-download",
            "Transcribing": "v1/transcribe-and-diarize",
            "Segmenting": "v1/extract-topical-segments",
            "Summarizing Segments": "v1/summarise-segments",
            "Create TikTok Ideas": "v1/generate-short-ideas"
        }

        if new_status in status_route_mapping:
            api_route = status_route_mapping[new_status]
            process_video_upload(project_id, jwt_secret_key, ip_address, api_route, document_id)
    else:
        print("Preprocessing stage triggered... Nothing happened.")

