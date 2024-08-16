import os
from google.cloud import tasks_v2, firestore
import datetime
import jwt
from dotenv import load_dotenv

load_dotenv()

# Get environment variables
IP_ADDRESS = os.getenv("BACKEND_SERVICE_ADDRESS")
PROJECT_ID = os.getenv("PROJECT_ID")
JWT_SECRET_KEY = os.getenv("SECRET_KEY")
QUEUE_NAME = 'viranova-preprocessing-queue'
QUEUE_LOCATION = 'europe-west3'


def create_jwt_token(secret_key, payload):
    payload['exp'] = datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
    return jwt.encode(payload, secret_key, algorithm='HS256')


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
    print(f'Task created: {response.name}')


def process_request(request_id, request_endpoint):
    url = f'{IP_ADDRESS}/{request_endpoint}/{request_id}'
    payload = {
        'request_id': request_id,
        'request_endpoint': request_endpoint
    }
    token = create_jwt_token(JWT_SECRET_KEY, payload)
    client = tasks_v2.CloudTasksClient()
    create_task(client, PROJECT_ID, QUEUE_NAME, token, QUEUE_LOCATION, url)


def handle_request(event, context):
    """
    Handle the creation or update of a request document.
    """
    db = firestore.Client()

    # Get the document that triggered the function
    doc_path = context.resource
    request_doc = db.document(doc_path).get()
    request_data = request_doc.to_dict()
    request_id = doc_path.split('/')[-1]

    if not request_data:
        print(f"Error: Request {request_id} data is empty")
        return

    # Stage 1: Server acknowledgment
    if 'requestAcknowledgedTimestamp' not in request_data:
        print(f"Acknowledging new request: {request_id}")
        db.document(doc_path).update({
            "requestAcknowledgedTimestamp": firestore.SERVER_TIMESTAMP
        })
        return

    # Stage 2: Sending to Cloud Tasks queue
    if 'serverStartedTimestamp' not in request_data:
        request_endpoint = request_data.get('requestEndpoint')

        if request_endpoint:
            print(f"Processing request: {request_id} with endpoint: {request_endpoint}")
            process_request(request_id, request_endpoint)

        else:
            print(f"Error: Request {request_id} is missing requestEndpoint")
    else:
        print(f"Request {request_id} has already been sent to Cloud Tasks")


# Cloud Function entry point
def on_request_created_or_updated(event, context):
    """Triggered by a change to a Firestore document."""
    handle_request(event, context)