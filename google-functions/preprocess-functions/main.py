import requests


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

    def process_video_upload(ip_address, api_route, video_id):
        # Example API endpoint
        url = f'{ip_address}/{api_route}/{video_id}'
        print("Making Request to: ", url)

        # Make a GET request to the API
        response = requests.get(url)

        # Check if the request was successful
        if response.status_code == 200:
            # Process the response data (assuming JSON)
            data = response.json()
            return f"Success: {data}"
        else:
            return f"Failed to fetch data, status code: {response.status_code}"

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

