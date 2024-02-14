import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from firebase_admin import storage
import os
from dotenv import load_dotenv
from io import BytesIO

from google.protobuf.json_format import MessageToDict

load_dotenv()

class FirebaseService:
    def __init__(self):
        # Initialize the app with a service account, granting admin privileges
        self.cred = credentials.Certificate('./viranova-firebase-service-account.json')
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
            update_progress(index/(len(transcribed_content.results) - 1) * 100)
            primary_alternative = result.alternatives[0]

            transcript_data = {
                'transcript': primary_alternative.transcript,
                'confidence': primary_alternative.confidence,
                'video_id': video_id,  # Linking back to the original video
                # Assuming you have a way to determine or set the language code
                'language_code': "en-US"  # Example, adjust as needed
            }

            # Create a new document for this transcript in Firestore
            transcript_doc_ref = transcriptions_collection.document()
            transcript_doc_ref.set(transcript_data)
            transcripts_list.append(transcript_data)

            # Process and upload each word in the 'words' of the alternative
            words_collection_ref = transcript_doc_ref.collection('words')
            for word_info in primary_alternative.words:
                # Handle potentially converted Duration fields (to datetime.timedelta)
                start_time_seconds = word_info.start_time.total_seconds() if word_info.start_time else 0
                end_time_seconds = word_info.end_time.total_seconds() if word_info.end_time else 0

                word_data = {
                    'word': word_info.word,
                    'start_time': start_time_seconds,
                    'end_time': end_time_seconds,
                    'speaker_tag': word_info.speaker_tag
                }
                words_collection_ref.add(word_data)
                words_list.append(word_data)

        return transcripts_list, words_list