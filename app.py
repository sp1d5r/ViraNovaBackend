from flask import Flask
from routes.generate_short_ideas import generate_short_ideas
from routes.get_random_video import get_random_video
from routes.get_segmentation_masks import get_segmentation_mask
from routes.get_shorts_and_segments import get_shorts_and_segments
from routes.spacial_segmentation import spacial_segmentation
from routes.summarise_segments import summarise_segments
from routes.temporal_segmentation import temporal_segmentation
from routes.transcribe_and_diarize_audio import transcribe_and_diarize_audio
from routes.split_video_and_audio import split_video_and_audio
from routes.topical_segmentation import topical_segmentation
from flask_cors import CORS

from routes.youtube_link import youtube_link

app = Flask(__name__)

origins = [
    "http://localhost:3000/segmentation",
    "https://master.d2gor5eji1mb54.amplifyapp.com",
    "http://localhost:5000",
    "http://localhost:8000",
    "http://localhost:3000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:5000"
    "http://127.0.0.1:3000"
]

CORS(app, resources={r"/*": {"origins": origins}})

# Registering Routes
app.register_blueprint(split_video_and_audio)
app.register_blueprint(transcribe_and_diarize_audio)
app.register_blueprint(topical_segmentation)
app.register_blueprint(summarise_segments)
app.register_blueprint(get_random_video)
app.register_blueprint(get_segmentation_mask)
app.register_blueprint(get_shorts_and_segments)
app.register_blueprint(generate_short_ideas)
app.register_blueprint(temporal_segmentation)
app.register_blueprint(spacial_segmentation)
app.register_blueprint(youtube_link)


@app.route("/")
def main_route():
    return "Viranova Backend"


if __name__ == '__main__':
    app.run(port=5000, debug=False)
