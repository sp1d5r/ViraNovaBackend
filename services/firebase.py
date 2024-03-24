import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from firebase_admin import storage
import base64
import os
import json
from dotenv import load_dotenv
from io import BytesIO
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

    def upload_transcription_to_firestore(self, transcribed_content, video_id, update_progress):
        transcriptions_collection = self.db.collection('transcriptions')
        transcripts_list = []
        words_list = []

        for index, result in enumerate(transcribed_content.results):
            update_progress(index / (len(transcribed_content.results) - 1) * 100)
            primary_alternative = result.alternatives[0]

            # Initialize with 'None' to identify if start or end times have not been set
            earliest_start_time = None
            latest_end_time = None

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

    def query_transcripts_by_video_id(self, video_id):
        # New method to query transcripts by video_id and sort by index
        transcripts = self.db.collection("transcriptions") \
            .where("video_id", "==", video_id) \
            .order_by("index") \
            .get()

        return [transcript.to_dict() for transcript in transcripts]

    def query_transcripts_by_video_id_with_words(self, video_id):
        # Query transcripts by video_id and sort by index
        transcripts = self.db.collection("transcriptions") \
            .where("video_id", "==", video_id) \
            .order_by("index") \
            .get()

        # Initialize a list to hold all transcripts with their words
        transcripts_with_words = []

        # Iterate over each transcript document
        for transcript in transcripts:
            # Convert the transcript document to a dictionary
            transcript_dict = transcript.to_dict()

            # Fetch words for the current transcript from the "word" sub-collection
            words = self.db.collection("transcriptions") \
                .document(transcript.id) \
                .collection("words") \
                .order_by("index") \
                .get()

            # Add the words to the transcript dictionary
            transcript_dict["words"] = [word.to_dict() for word in words]

            # Append the enriched transcript to the list
            transcripts_with_words.append(transcript_dict)

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
