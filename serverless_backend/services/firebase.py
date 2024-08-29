import tempfile

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from google.cloud import firestore as fs
from firebase_admin import storage
import base64
import os
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv
from io import BytesIO
import pandas as pd
load_dotenv()


class FirebaseService:
    def __init__(self):
        # Initialize the app with a service account, granting admin privileges
        encoded_json_str = os.getenv('SERVICE_ACCOUNT_ENCODED')
        json_str = base64.b64decode(encoded_json_str).decode('utf-8')
        service_account_info = json.loads(json_str)
        self.cred = credentials.Certificate(service_account_info)
        storage_bucket = os.getenv('FIREBASE_STORAGE_BUCKET')
        if not firebase_admin._apps:
            self.app = firebase_admin.initialize_app(self.cred, {
                'storageBucket': storage_bucket
            })
        self.db = firestore.client()
        self.bucket = storage.bucket()

    def get_document(self, collection_name, document_id):
        # Retrieve an instance of a CollectionReference
        doc_ref = self.db.collection(collection_name).document(document_id)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        else:
            return None

    def add_document(self, collection_name, document_data):
        """Adds a new document with given data to a specified collection."""
        collection_ref = self.db.collection(collection_name)
        # Add a new document
        document_ref = collection_ref.add(document_data)
        # Return the new document's reference (ID)
        return document_ref[1].id  # document_ref is a tuple of (DocumentReference, datetime), we need the ID

    def get_all_documents(self, collection_name):
        """Fetches all documents from a specified collection."""
        collection_ref = self.db.collection(collection_name)
        docs = collection_ref.stream()
        return [doc.to_dict() for doc in docs]

    def download_file(self, blob_name, destination_file_name):
        """Downloads a file from Firebase Storage."""
        blob = self.bucket.blob(blob_name)
        blob.download_to_filename(destination_file_name)
        return f"File downloaded to {destination_file_name}."

    def download_file_to_memory(self, blob_name):
        """Downloads a file from Firebase Storage to memory."""
        blob = self.bucket.blob(blob_name)
        in_memory_file = BytesIO()
        blob.download_to_file(in_memory_file)
        in_memory_file.seek(0)  # Move to the beginning of the BytesIO buffer
        return in_memory_file

    def update_message(self,  document_id, message):
        try:
            # Get a reference to the document
            doc_ref = self.db.collection("requests").document(document_id)

            # Get the current document
            doc = doc_ref.get()

            # Prepare the new log entry
            new_log = {
                "message": message,
                "timestamp": datetime.now()
            }

            # Get the current logs or initialize an empty list
            current_logs = doc.to_dict().get("logs", []) if doc.exists else []

            # Append the new log
            updated_logs = current_logs + [new_log]

            # Update the document
            doc_ref.update({
                "logs": updated_logs,
                "progress_message": message,
                "last_updated": datetime.now()
            })

            print(f"Successfully updated message for {document_id}, {message}")
        except Exception as e:
            print(f"Failed to update message: {str(e)}")

    def create_short_request(self, endpoint: str, short_id: str, uid: str):
        # Define valid endpoints and their associated credit costs
        valid_endpoints = {
            "v1/temporal-segmentation": 1,
            "v1/generate-test-audio": 1,
            "v1/generate-intro": 1,
            "v1/create-short-video": 2,
            "v1/get_saliency_for_short": 2,
            "v1/determine-boundaries": 1,
            "v1/get-bounding-boxes": 2,
            "v1/generate-a-roll": 2,
            "v1/generate-intro-video": 2,
            "v1/generate-b-roll": 2,
            "v1/create-cropped-video": 2
        }

        # Validate endpoint
        if endpoint not in valid_endpoints:
            raise ValueError(f"Invalid endpoint: {endpoint}")

        # Get the credit cost for the endpoint
        credit_cost = valid_endpoints[endpoint]

        # Check if user has enough credits
        user_doc = self.db.collection("users").document(uid).get()
        if not user_doc.exists:
            raise ValueError(f"User {uid} not found")

        user_data = user_doc.to_dict()
        user_credits = user_data.get('credits', {}).get('current', 0)

        if user_credits < credit_cost:
            raise ValueError(f"Insufficient credits to continue autogenerate for request {endpoint} Required: {credit_cost}, Available: {user_credits}")

        # Create the request document
        request = {
            "requestOperand": "short",
            "requestEndpoint": endpoint,
            "requestCreated": fs.SERVER_TIMESTAMP,
            "uid": uid,
            "shortId": short_id,
            "creditCost": credit_cost,
            "status": "pending"
        }

        print("Creating request", request)

        # Add the document to Firestore
        try:
            doc_ref = self.db.collection("requests").add(request)
            request_id = doc_ref[1].id
            print(f"Request created with ID: {request_id}")
            return request_id
        except Exception as e:
            print(f"Error creating request: {str(e)}")
            raise

    def download_file_to_temp(self, blob_name, suffix=".mp4"):
        """Downloads a file from Firebase Storage to a temporary file and returns the file path."""
        blob = self.bucket.blob(blob_name)
        _, temp_local_path = tempfile.mkstemp(suffix=suffix)
        blob.download_to_filename(temp_local_path)
        return temp_local_path

    def upload_file_from_temp(self, file_path, destination_blob_name):
        """Uploads a file from a temporary file to Firebase Storage."""
        blob = self.bucket.blob(destination_blob_name)
        blob.upload_from_filename(file_path)
        os.remove(file_path)

    def upload_file_from_memory(self, in_memory_file, destination_blob_name):
        """Uploads a file from memory to Firebase Storage."""
        blob = self.bucket.blob(destination_blob_name)
        in_memory_file.seek(0)  # Move to the beginning of the BytesIO buffer
        blob.upload_from_file(in_memory_file)

    def update_document(self, collection_name, document_id, update_fields):
        """Updates specific fields of a document."""
        doc_ref = self.db.collection(collection_name).document(document_id)
        doc_ref.update(update_fields)
        return f"Document {document_id} in {collection_name} updated."

    def upload_audio_file_from_memory(self, blob_name, file_bytes):
        """Uploads a file to Firebase Storage from memory."""
        blob = self.bucket.blob(blob_name)
        blob.upload_from_string(file_bytes, content_type='audio/mp4')
        return f"File {blob_name} uploaded."

    def get_signed_url(self, blob_name, expiration=3600):
        """
        Generate a signed URL for a file in Firebase Storage.

        :param blob_name: The name of the blob in Firebase Storage
        :param expiration: The number of seconds until the signed URL expires (default is 1 hour)
        :return: The signed URL as a string
        """
        blob = self.bucket.blob(blob_name)

        # Generate a signed URL that expires after the specified time
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.utcnow() + timedelta(seconds=expiration),
            method="GET",
        )

        return url

    def upload_transcription_to_firestore(self, transcribed_content, video_id, update_progress):
        previous_transcripts = self.query_documents("transcriptions", "video_id", video_id)

        print("Previous Transcripts", previous_transcripts)
        if previous_transcripts and len(previous_transcripts) > 0:
            for transcripts in previous_transcripts:
                self.delete_document('transcriptions', transcripts['id'])

        transcriptions_collection = self.db.collection('transcriptions')
        transcripts_list = []
        words_list = []
        earliest_start_time = None
        latest_end_time = None

        for index, result in enumerate(transcribed_content.results):
            update_progress(index / (len(transcribed_content.results) - 1) * 100)
            primary_alternative = result.alternatives[0]

            words_data = []  # To temporarily store word data and calculate times

            for word_index, word_info in enumerate(primary_alternative.words):
                # Convert to total seconds from timedelta
                start_time_seconds = word_info.start_time.total_seconds() if word_info.start_time else None
                end_time_seconds = word_info.end_time.total_seconds() if word_info.end_time else None

                # Update earliest and latest times
                if start_time_seconds is not None:
                    if earliest_start_time is None or start_time_seconds < earliest_start_time:
                        earliest_start_time = start_time_seconds

                if end_time_seconds is not None:
                    if latest_end_time is None or end_time_seconds > latest_end_time:
                        latest_end_time = end_time_seconds

                word_data = {
                    'word': word_info.word,
                    'start_time': start_time_seconds,
                    'end_time': end_time_seconds,
                    'speaker_tag': word_info.speaker_tag,
                    'index': word_index
                }
                words_data.append(word_data)

            words_list.extend(words_data)

            # Create a new document for this transcript in Firestore
            transcript_doc_ref = transcriptions_collection.document()
            transcript_data = {
                'transcript': primary_alternative.transcript,
                'confidence': primary_alternative.confidence,
                'video_id': video_id,
                'language_code': "en-US",  # Example, adjust as needed
                'earliest_start_time': earliest_start_time,
                'latest_end_time': latest_end_time,
                'index': index
            }

            transcript_doc_ref.set(transcript_data)

            # Now add words to the words sub collection
            words_collection_ref = transcript_doc_ref.collection('words')
            for word_data in words_data:
                words_collection_ref.add(word_data)
            transcripts_list.append(transcript_data)

        return transcripts_list, words_list

    def upload_deepgram_transcription_to_firestore(self, transcription_data, video_id, update_progress):
        # Delete previous transcripts
        previous_transcripts = self.query_documents("transcriptions", "video_id", video_id)
        if previous_transcripts:
            doc_ids = [transcript['id'] for transcript in previous_transcripts]
            self.batch_delete_documents('transcriptions', doc_ids)
            update_progress(50)  # 50% progress after deletion

        transcriptions_collection = self.db.collection('transcriptions')

        # Convert words to DataFrame for easier processing
        words_df = pd.DataFrame(transcription_data['words'])

        # Group words into utterances (you can adjust the grouping logic as needed)
        words_df['group_index'] = words_df.index // 10  # Group every 10 words, adjust as needed

        grouped_df = words_df.groupby('group_index')
        total_groups = len(grouped_df)

        # Prepare batches for efficient writing
        batch = self.db.batch()
        batch_count = 0
        max_batch_size = 500  # Firestore allows up to 500 operations per batch

        for index, (group_index, group) in enumerate(grouped_df):
            update_progress(50 + (index / total_groups * 50))  # Last 50% for uploading

            transcript_id = f"{video_id}_{group_index}"
            transcript_doc_ref = transcriptions_collection.document(transcript_id)

            transcript_data = {
                'transcript': ' '.join(group['word'].tolist()),
                'confidence': float(group['confidence'].mean()),
                'video_id': video_id,
                'language_code': group['language'].iloc[0],
                'earliest_start_time': float(group['start_time'].min()),
                'latest_end_time': float(group['end_time'].max()),
                'index': group_index,
                'words': group.to_dict('records')
            }

            batch.set(transcript_doc_ref, transcript_data)
            batch_count += 1

            if batch_count >= max_batch_size:
                batch.commit()
                batch = self.db.batch()
                batch_count = 0

        # Commit any remaining operations
        if batch_count > 0:
            batch.commit()

        return self.query_transcripts_by_video_id(video_id)

    def upload_youtube_transcription_to_firestore(self, transcribed_df, video_id, update_progress):
        # Delete previous transcripts
        previous_transcripts = self.query_documents("transcriptions", "video_id", video_id)
        if previous_transcripts:
            doc_ids = [transcript['id'] for transcript in previous_transcripts]
            self.batch_delete_documents('transcriptions', doc_ids)
            update_progress(50)  # 50% progress after deletion

        transcriptions_collection = self.db.collection('transcriptions')

        # Group by 'group_index' to handle multiple words belonging to the same transcript
        grouped_df = transcribed_df.groupby('group_index')
        total_groups = len(grouped_df)

        # Prepare batches for efficient writing
        batch = self.db.batch()
        batch_count = 0
        max_batch_size = 500  # Firestore allows up to 500 operations per batch

        for index, (group_index, group) in enumerate(grouped_df):
            update_progress(50 + (index / total_groups * 50))  # Last 50% for uploading

            transcript_id = f"{video_id}_{group_index}"
            transcript_doc_ref = transcriptions_collection.document(transcript_id)

            transcript_data = {
                'transcript': ' '.join(group['word'].tolist()),
                'confidence': float(group['confidence'].mean()),
                'video_id': video_id,
                'language_code': group['language'].iloc[0],
                'earliest_start_time': float(group['start_time'].min()),
                'latest_end_time': float(group['end_time'].max()),
                'index': group_index,
                'words': group.to_dict('records')  # Store all words data directly in the transcript document
            }

            batch.set(transcript_doc_ref, transcript_data)
            batch_count += 1

            if batch_count >= max_batch_size:
                batch.commit()
                batch = self.db.batch()
                batch_count = 0

        # Commit any remaining operations
        if batch_count > 0:
            batch.commit()

        return self.query_transcripts_by_video_id(video_id)

    def query_transcripts_by_video_id(self, video_id):
        # New method to query transcripts by video_id and sort by index
        transcripts = self.db.collection("transcriptions") \
            .where("video_id", "==", video_id) \
            .order_by("index") \
            .get()

        return [transcript.to_dict() for transcript in transcripts]

    def batch_delete_documents(self, collection_name, document_ids):
        """Deletes multiple documents in batches."""
        batch = self.db.batch()
        batch_count = 0
        max_batch_size = 500  # Firestore allows up to 500 operations per batch

        for doc_id in document_ids:
            doc_ref = self.db.collection(collection_name).document(doc_id)
            batch.delete(doc_ref)
            batch_count += 1

            if batch_count >= max_batch_size:
                batch.commit()
                batch = self.db.batch()
                batch_count = 0

        # Commit any remaining operations
        if batch_count > 0:
            batch.commit()

    def batch_add_documents(self, collection_name, documents):
        """
        Adds multiple documents to a collection in batches.

        :param collection_name: Name of the collection to add documents to
        :param documents: List of dictionaries, each representing a document to add
        """
        batch = self.db.batch()
        batch_size = 0
        max_batch_size = 500  # Firestore allows up to 500 operations per batch

        for doc in documents:
            # Create a reference to a new document with an auto-generated ID
            doc_ref = self.db.collection(collection_name).document()
            batch.set(doc_ref, doc)
            batch_size += 1

            if batch_size >= max_batch_size:
                # Commit the batch
                batch.commit()
                # Start a new batch
                batch = self.db.batch()
                batch_size = 0

        # Commit any remaining operations
        if batch_size > 0:
            batch.commit()

    def delete_document(self, collection_name, document_id):
        """Deletes a specific document and its subcollections."""
        doc_ref = self.db.collection(collection_name).document(document_id)
        doc = doc_ref.get()
        if doc.exists:
            # Delete subcollections first
            # Assuming we know the names of subcollections or we retrieve them dynamically
            subcollections = doc.reference.collections()  # List subcollections
            for subcollection in subcollections:
                self.delete_collection(subcollection, batch_size=500)

            # Now delete the document
            doc_ref.delete()
            return f"Document {document_id} in {collection_name} deleted successfully."
        else:
            return f"Document {document_id} in {collection_name} does not exist."

    def delete_collection(self, coll_ref, batch_size):
        """Deletes a collection in batches."""
        docs = coll_ref.limit(batch_size).stream()
        deleted = 0

        for doc in docs:
            doc.reference.delete()
            deleted += 1

        if deleted >= batch_size:
            self.delete_collection(coll_ref, batch_size)

    def query_transcripts_by_video_id_with_words(self, video_id):
        # Query transcripts by video_id and sort by index
        transcripts = self.db.collection("transcriptions") \
            .where("video_id", "==", video_id) \
            .order_by("index") \
            .get()

        # Convert the documents to dictionaries
        # The words are now directly included in each transcript document
        transcripts_with_words = [transcript.to_dict() for transcript in transcripts]

        return transcripts_with_words

    def query_topical_segments_by_video_id(self, video_id):
        # New method to query transcripts by video_id and sort by index
        segments = self.db.collection("topical_segments") \
            .where("video_id", "==", video_id) \
            .order_by("index") \
            .get()

        segments_with_ids = []
        for segment in segments:
            segment_dict = segment.to_dict()  # Convert to dictionary
            segment_dict['id'] = segment.id  # Add the document ID with key 'id'
            segments_with_ids.append(segment_dict)

        return segments_with_ids

    def query_documents(self, collection, field, value):
        # New method to query transcripts by video_id and sort by index
        query_res = self.db.collection(collection) \
            .where(field, "==", value) \
            .get()

        response = []
        for query in query_res:
            qeury_dict = query.to_dict()
            qeury_dict['id'] = query.id
            response.append(qeury_dict)

        return response

    def delete_collection(self, coll_ref, batch_size):
        """Recursively delete a collection in batches."""
        docs = coll_ref.limit(batch_size).stream()
        deleted = 0

        for doc in docs:
            print(f'Deleting doc {doc.id} => {doc.to_dict()}')
            doc.reference.delete()
            deleted = deleted + 1

        if deleted >= batch_size:
            return self.delete_collection(coll_ref, batch_size)
