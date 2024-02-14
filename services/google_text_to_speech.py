from google.cloud import speech
from google.oauth2 import service_account
from dotenv import load_dotenv
import os

load_dotenv()

class GoogleSpeechService:
    def __init__(self, credentials_path='./viranova-firebase-service-account.json'):
        self.credentials = service_account.Credentials.from_service_account_file(credentials_path)
        self.client = speech.SpeechClient(credentials=self.credentials)
        self.storage_bucket = os.getenv('FIREBASE_STORAGE_BUCKET')

    def transcribe_file(self, file_path,  update_progress, update_progress_message, language='en-US', enable_diarization=False, diarization_speaker_count=2):
        """
        Transcribes the given audio file using Google Cloud Speech-to-Text.

        :param file_path: Path to the audio file to transcribe.
        :param language: The language of the audio file.
        :param enable_diarization: Whether to enable speaker diarization.
        :param diarization_speaker_count: The number of speakers in the audio file.
        :return: The transcription result.
        """
        with open(file_path, 'rb') as audio_file:
            content = audio_file.read()

        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=language,
            enable_speaker_diarization=enable_diarization,
            diarization_speaker_count=diarization_speaker_count
        )

        update_progress_message("Begining Speech Recognition")
        response = self.client.recognize(config=config, audio=audio)

        update_progress_message("Speech Recognition Complete!")
        # For diarization results: response.results[-1].alternatives[0].words
        for index, result in enumerate(response.results):
            update_progress((index/len(response.results)) * 100)
            print("Transcript: {}".format(result.alternatives[0].transcript))
            if enable_diarization:
                # Show speaker tags if diarization is enabled
                for word_info in result.alternatives[0].words:
                    print(f"Speaker {word_info.speaker_tag}: '{word_info.word}'")

        return response

    def transcribe_gcs(self, audio_path, update_progress, update_progress_message, language='en-US', enable_diarization=False, diarization_speaker_count=2):
        """
        Transcribes the given audio file from Google Cloud Storage using Google Cloud Speech-to-Text.

        :param audio_path: The URI of the audio file in Google Cloud Storage (e.g., 'gs://your-bucket/your-file.wav').
        :param language: The language of the audio file.
        :param enable_diarization: Whether to enable speaker diarization.
        :param diarization_speaker_count: The number of speakers in the audio file.
        :return: The transcription result.
        """
        print("gs://"+self.storage_bucket + audio_path)
        audio = speech.RecognitionAudio(uri="gs://"+self.storage_bucket + "/" + audio_path)

        if enable_diarization:
            diarization_config = speech.SpeakerDiarizationConfig(
                enable_speaker_diarization=True,
                min_speaker_count=1,
                max_speaker_count=10,
            )

            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code=language,
                diarization_config=diarization_config,
            )
        else:
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code=language,
            )


        update_progress_message("Beginning Speech Recognition")
        response = self.client.recognize(config=config, audio=audio)
        update_progress_message("Speech Recognition Complete!")

        # For diarization results: response.results[-1].alternatives[0].words
        for index, result in enumerate(response.results):
            update_progress(index / (len(response.results) - 1) * 100)
            print("Transcript: {}".format(result.alternatives[0].transcript))
            if enable_diarization:
                # Show speaker tags if diarization is enabled
                for word_info in result.alternatives[0].words:
                    print(f"Speaker {word_info.speaker_tag}: '{word_info.word}'")

        return response

# Example usage:
# Assuming you've saved your service account credentials to 'path/to/your/service-account-file.json'
# and have an audio file 'path/to/your/audio-file.wav'

# service = GoogleSpeechService('path/to/your/service-account-file.json')
# service.transcribe_file('path/to/your/audio-file.wav', enable_diarization=True)


# Example GCS URI
# gcs_uri = 'gs://your-bucket-name/your-audio-file.wav'

# # Assuming you've initialized your GoogleSpeechService instance as `service`
# response = service.transcribe_gcs(gcs_uri, enable_diarization=True)
