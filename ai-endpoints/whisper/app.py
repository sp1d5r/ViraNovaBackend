"""
A minimal example app which takes a Youtube URL as input and transcribes the video with OpenAI's Whisper.
"""
from beam import App, Runtime, Image, Output, Volume
import os


app = App(
    name="whisper-example",
    runtime=Runtime(
        cpu=1,
        memory="32Gi",
        gpu="A10G",
        image=Image(
            python_version="python3.8",
            python_packages=[
                "git+https://github.com/openai/whisper.git",
                "pytube @ git+https://github.com/felipeucelli/pytube@03d72641191ced9d92f31f94f38cfb18c76cfb05",
            ],
            commands=["apt-get update && apt-get install -y ffmpeg"],
        ),
    ),
)


def load_models():
    model = whisper.load_model("small")
    return model


# This is deployed as a REST API, but for longer videos
# you'll want to deploy as an async task queue instead, since the
# REST API has a 60s timeout
@app.rest_api(outputs=[Output(path="video.mp3")], loader=load_models)
def transcribe(**inputs):
    # Grab the video URL passed from the API
    try:
        video_url = inputs["video_id"]
    # Use a default input if none is provided
    except KeyError:
        return {"error": "No video incorrect video entered"}
    

    return {"pred": result["text"]}


if __name__ == "__main__":
    transcribe(video_url=video_url)
