import os
from typing import Optional
from elevenlabs import save, VoiceSettings
from elevenlabs.client import ElevenLabs


class ElevenLabsTTSService:
    def __init__(self, api_key=None):
        self.api_key = os.getenv('ELEVENLABS_API_KEY', api_key)
        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY environment variable is not set")
        self.client = ElevenLabs(api_key=self.api_key)

    def generate_speech(self, text: str, output_filename: str, voice_id: str = "N2lVS1w4EtoT3dr4eOWO") -> str:
        """
        Generate speech from text using ElevenLabs' TTS service.

        :param text: The text to convert to speech
        :param output_filename: The name of the output audio file
        :param voice_id: The voice ID to use (default is "bIHbv24MWmeRgasZH58o")
        :return: The path to the generated audio file
        """
        try:
            audio = self.client.text_to_speech.convert(
                voice_id=voice_id,
                optimize_streaming_latency="0",
                output_format="mp3_44100_128",
                text=text,
                voice_settings=VoiceSettings(
                    stability=0.5,
                    similarity_boost=0.5,
                    style=0.0,
                ),
            )

            save(audio, output_filename)

            print(f"Speech generated successfully. Saved to {output_filename}")
            return output_filename

        except Exception as e:
            print(f"Error generating speech: {str(e)}")
            return ""


def generate_ai_voiceover(text: str, output_path: str, voice_id: Optional[str] = None) -> str:
    """
    Generate an AI voiceover using ElevenLabs' TTS service.

    :param text: The text to convert to speech
    :param output_path: The path where the audio file will be saved
    :param voice_id: Optional voice ID to use (default will be used if not provided)
    :return: The path to the generated audio file
    """
    tts_service = ElevenLabsTTSService()
    return tts_service.generate_speech(text, output_path, voice_id or "N2lVS1w4EtoT3dr4eOWO")


# Example usage
if __name__ == "__main__":
    intro_text = "This is why you should NEVER focus on the stock price."
    output_file = "intro_voiceover.mp3"

    generated_audio_path = generate_ai_voiceover(intro_text, output_file)
    if generated_audio_path:
        print(f"Voiceover generated and saved to: {generated_audio_path}")
    else:
        print("Failed to generate voiceover.")