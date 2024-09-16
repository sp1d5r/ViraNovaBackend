import google.cloud.firestore
import os
from dotenv import load_dotenv
from google.cloud import tasks_v2
import datetime
import jwt
import requests
import json

def create_jwt_token(secret_key, payload):
    payload['exp'] = datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
    token = jwt.encode(payload, secret_key, algorithm='HS256')
    return token

def create_client():
    return tasks_v2.CloudTasksClient()

def create_task(client, project, queue, token, location, url):
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
    response = client.create_task(request={"parent": parent, "task": task})
    print('Task created: {}'.format(response.name))

def process_api_call(project_id, jwt_secret, ip_address, api_route, doc_id):
    project = project_id
    queue = 'viranova-preprocessing-queue'
    location = 'europe-west3'
    url = f'{ip_address}/{api_route}/{doc_id}'

    payload = {
        'doc_id': doc_id,
        'api_route': api_route
    }

    token = create_jwt_token(jwt_secret, payload)
    client = create_client()
    create_task(client, project, queue, token, location, url)

def image_document_listener(event, context):
    load_dotenv()

    ip_address = os.getenv("BACKEND_SERVICE_ADDRESS")
    project_id = os.getenv("PROJECT_ID")
    jwt_secret_key = os.getenv("SECRET_KEY")

    db = google.cloud.firestore.Client()

    doc_path = context.resource
    changed_doc = db.document(doc_path).get()
    data = changed_doc.to_dict()
    image_id = doc_path.split('/')[-1]

    if data and 'status' in data and data['status'] == 'pending':
        print(f"New image document created with ID: {image_id}")

        # Trigger the image generation process
        api_route = "v1/generate-images"
        process_api_call(project_id, jwt_secret_key, ip_address, api_route, image_id)
    else:
        print(f"Image document {image_id} updated, but no action needed.")
