import os
from typing import Optional
from deepgram import DeepgramClient, SpeakOptions


class DeepgramTTSService:
    def __init__(self):
        self.api_key = os.getenv('DEEP_GRAM_API_KEY')
        if not self.api_key:
            raise ValueError("DEEP_GRAM_API_KEY environment variable is not set")
        self.client = DeepgramClient(self.api_key)

    def generate_speech(self, text: str, output_filename: str, model: str = "aura-orion-en") -> str:
        """
        Generate speech from text using Deepgram's TTS service.

        :param text: The text to convert to speech
        :param output_filename: The name of the output audio file
        :param model: The TTS model to use (default is "aura-orion-en")
        :return: The path to the generated audio file
        """
        try:
            options = SpeakOptions(
                model=model,
            )

            response = self.client.speak.v("1").save(output_filename, {"text": text}, options)

            print(f"Speech generated successfully. Saved to {output_filename}")
            print(response.to_json(indent=4))

            return output_filename

        except Exception as e:
            print(f"Error generating speech: {str(e)}")
            return ""


def generate_ai_voiceover(text: str, output_path: str, model: Optional[str] = None) -> str:
    """
    Generate an AI voiceover using Deepgram's TTS service.

    :param text: The text to convert to speech
    :param output_path: The path where the audio file will be saved
    :param model: Optional model to use (default will be used if not provided)
    :return: The path to the generated audio file
    """
    tts_service = DeepgramTTSService()
    return tts_service.generate_speech(text, output_path, model or "aura-orion-en")


# Example usage
if __name__ == "__main__":
    intro_text = "This is why you should never focus on the stock price."
    output_file = "intro_voiceover.mp3"

    generated_audio_path = generate_ai_voiceover(intro_text, output_file)
    if generated_audio_path:
        print(f"Voiceover generated and saved to: {generated_audio_path}")
    else:
        print("Failed to generate voiceover.")