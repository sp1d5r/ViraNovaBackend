import functions_framework
from google.cloud import firestore
from datetime import datetime, timedelta
import requests
import os

# Initialize Firestore client
db = firestore.Client()

# Backend service URL
BACKEND_SERVICE_URL = os.environ.get('BACKEND_SERVICE_URL', 'https://get-fucked-buddy.com/process-task')


@functions_framework.http
def check_and_process_tasks(request):
    # Get current time
    now = datetime.utcnow()

    # Query for tasks that are scheduled within the next 10 minutes
    tasks_ref = db.collection('tasks')
    upcoming_tasks = tasks_ref.where('status', '==', 'Pending') \
        .where('scheduledTime', '<=', now + timedelta(minutes=10)) \
        .stream()

    processed_tasks = 0

    for task in upcoming_tasks:
        task_data = task.to_dict()

        # Call the backend service to process the task
        try:
            task.reference.update({
                'status': 'Running',
                'processingStartTime': firestore.SERVER_TIMESTAMP
            })

            if task_data.get('operation') == 'Analytics':
                endpoint = BACKEND_SERVICE_URL + '/v1/collect-tiktok-data/' + task_data.get('shortId') + '/' + task_data.get('taskResultId')


                response = requests.get(endpoint)

                if response.status_code == 200:
                    # Update task status to 'Running'
                    task.reference.update({
                        'status': 'Complete',
                        'processingStartTime': firestore.SERVER_TIMESTAMP
                    })
                    processed_tasks += 1
                else:
                    task.reference.update({
                        'status': 'Failed',
                        'processingStartTime': firestore.SERVER_TIMESTAMP
                    })
                    print(f"Failed to process task {task.id}: {response.text}")

        except requests.RequestException as e:
            print(f"Error calling backend service for task {task.id}: {str(e)}")

    return f"Processed {processed_tasks} tasks"
