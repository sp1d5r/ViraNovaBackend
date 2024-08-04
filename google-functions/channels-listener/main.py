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

def process_api_call(project_id, jwt_secret, ip_address, api_route, channel_id):
    project = project_id
    queue = 'viranova-preprocessing-queue'
    location = 'europe-west3'
    url = f'{ip_address}/{api_route}/{channel_id}'

    payload = {
        'channel_id': channel_id,
        'api_route': api_route
    }

    token = create_jwt_token(jwt_secret, payload)
    client = create_client()
    create_task(client, project, queue, token, location, url)



def subscribe_to_channel(channel_id):
    load_dotenv()

    WEBHOOK_URL = f"{os.getenv('BACKEND_SERVICE_ADDRESS')}/youtube-webhook"
    HUB_URL = 'https://pubsubhubbub.appspot.com/subscribe'

    topic_url = f'https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}'
    data = {
        'hub.callback': WEBHOOK_URL,
        'hub.topic': topic_url,
        'hub.verify': 'sync',
        'hub.mode': 'subscribe',
    }

    try:
        response = requests.post(HUB_URL, data=data)
        print(f"Response status code: {response.status_code}")
        print(f"Response headers: {json.dumps(dict(response.headers), indent=2)}")

        try:
            print(f"Response JSON: {json.dumps(response.json(), indent=2)}")
        except json.JSONDecodeError:
            print(f"Response text: {response.text}")

        if response.status_code == 202:
            print(f"Successfully subscribed to channel {channel_id}")
        else:
            print(f"Failed to subscribe to channel {channel_id}. Status code: {response.status_code}")

        # Now, let's make a GET request to your webhook to see how it responds
        webhook_response = requests.get(WEBHOOK_URL)
        print(f"\nWebhook GET response status code: {webhook_response.status_code}")
        print(f"Webhook GET response headers: {json.dumps(dict(webhook_response.headers), indent=2)}")

        try:
            print(f"Webhook GET response JSON: {json.dumps(webhook_response.json(), indent=2)}")
        except json.JSONDecodeError:
            print(f"Webhook GET response text: {webhook_response.text}")

    except Exception as e:
        print(f"Error subscribing to channel {channel_id}: {str(e)}")

def channel_document_listener(event, context):
    load_dotenv()

    ip_address = os.getenv("BACKEND_SERVICE_ADDRESS")
    project_id = os.getenv("PROJECT_ID")
    jwt_secret_key = os.getenv("SECRET_KEY")

    db = google.cloud.firestore.Client()

    doc_path = context.resource
    changed_doc = db.document(doc_path).get()
    data = changed_doc.to_dict()
    channel_id = doc_path.split('/')[-1]

    if data and 'status' in data and 'previous_status' in data and data['status'] != data['previous_status']:
        new_status = data['status']
        db.document(doc_path).update({"previous_status": new_status})
        print(f"Channel document with new status: {new_status}")

        # Check if the new status is the correct one to trigger the API call
        if new_status == 'New Channel':  # Replace 'correct_status' with the actual status you're looking for
            api_route = "v1/get-channel-information"
            process_api_call(project_id, jwt_secret_key, ip_address, api_route, channel_id)
            subscribe_to_channel(channel_id)
        else:
            print(f"Status changed to {new_status}, but no action needed.")
    else:
        print("Channel Listener Stage triggered... No status change detected.")
