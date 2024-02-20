import requests

import threading

def process_video_upload(ip_address, api_route, video_id):
    def make_request():
        url = f'{ip_address}/{api_route}/{video_id}'
        print("Making Request to: ", url)

        # Make a GET request to the API
        try:
            response = requests.get(url, timeout=10)  # Adding a timeout for good practice
            print(f"Request to {url} sent successfully.")
        except requests.RequestException as e:
            print(f"Failed to send request to {url}: {e}")

    # Start a new thread for the request
    thread = threading.Thread(target=make_request)
    thread.start()
    print(f"Request to {api_route} for video ID {video_id} is being processed in the background.")


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
            "Uploaded": "split-video",
            "Transcribing": "transcribe-and-diarize",
            "Segmenting": "extract-topical-segments",
            "Summarizing Segments": "summarise-segments",
        }

        if new_status in status_route_mapping:
            api_route = status_route_mapping[new_status]
            process_video_upload(ip_address, api_route, document_id)
    else:
        print("Data: ", data != None)
        print("Status in data", 'status' in data)
        print("Previous Status in data", 'previousStatus' in data)

