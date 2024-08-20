import os
from deepgram import DeepgramClient, PrerecordedOptions
from typing import Callable


class DeepgramTranscriberService:
    def __init__(self):
        self.api_key = os.getenv('DEEP_GRAM_API_KEY')
        self.client = DeepgramClient(self.api_key)

    def transcribe(self, audio_url: str, update_progress: Callable[[int], None],
                   update_progress_message: Callable[[str], None]) -> dict:
        try:
            update_progress_message("Starting transcription with Deepgram...")
            update_progress(10)

            options = PrerecordedOptions(
                model="nova-2",
                language="en",
                smart_format=True,
            )

            update_progress_message("Transcribing audio...")
            update_progress(30)

            response = self.client.listen.prerecorded.v("1").transcribe_url(
                {"url": audio_url},
                options,
                timeout=300
            )

            update_progress_message("Transcription complete. Processing results...")
            update_progress(80)

            # Process the response to match our required format
            processed_response = self._process_response(response)

            update_progress_message("Transcription processing complete.")
            update_progress(100)

            return processed_response

        except Exception as e:
            update_progress_message(f"Error during transcription: {str(e)}")
            raise

    def _process_response(self, response: dict) -> dict:
        results = response['results']
        channels = results['channels'][0]
        alternatives = channels['alternatives'][0]

        words = alternatives['words']

        # Process words to create our custom structure
        processed_words = []
        for i, word in enumerate(words):
            processed_word = {
                'word': word['punctuated_word'],
                'start_time': word['start'],
                'end_time': word['end'],
                'confidence': word['confidence'],
                'language': 'en',  # Assuming English, adjust if needed
                'group_index': i  # Each word is its own group in this case
            }
            processed_words.append(processed_word)

        return {
            'transcript': alternatives['transcript'],
            'words': processed_words,
            'confidence': alternatives['confidence']
        }