import os
import random
from flask import Blueprint, jsonify
from database.production_database import ProductionDatabase
from qdrant_client import QdrantClient, models

get_shorts_and_segments = Blueprint("get_shorts_and_segments", __name__)

@get_shorts_and_segments.route("/v2/get-random-short-video")
def get_random_short_video():
    database = ProductionDatabase()
    short_videos_embedded = database.read_table('videos_vectors_stored')
    video_id = random.choice(list(short_videos_embedded['video_id']))
    return video_id


@get_shorts_and_segments.route("/v2/get-short-and-segments")
def get_short_and_segments():
    database = ProductionDatabase()
    short_videos_embedded = database.read_table('videos_vectors_stored')

    if (len(short_videos_embedded['video_id']) <= 0):
        return jsonify({'error': 'POSTGRES DB: No short videos stored'})

    video_id = random.choice(list(short_videos_embedded['video_id']))
    qdrant = QdrantClient(os.getenv('QDRANT_LOCATION'))

    qdrant_query = qdrant.scroll(
        collection_name="videos_and_segments",
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="video_id",
                    match=models.MatchValue(value=video_id),
                ),
            ]
        ),
        with_vectors=True
    )

    if len(qdrant_query) == 0 or len(qdrant_query[0]) == 0:
        return jsonify({'error': 'QDRANT: Query returned no entries', 'video_id': video_id})

    query_doc = qdrant_query[0][0]

    response = qdrant.search(
        collection_name="videos_and_segments",
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="channel_id",
                    match=models.MatchValue(
                        value=query_doc.payload['channel_id'],
                    ),
                ),
                models.FieldCondition(
                    key="is_segment",
                    match=models.MatchValue(
                        value=True,
                    ),
                )
            ]
        ),
        search_params=models.SearchParams(hnsw_ef=128, exact=False),
        query_vector=query_doc.vector,
        limit=5,
    )

    if len(response) == 0:
        return jsonify({'error': f'QDRANT: No related videos for id {video_id}', 'video_id': video_id})
    else:
        similar_videos = [{**{'score': res.score}, **res.payload} for res in response]

        return jsonify({
            "search_video_id": video_id,
            'search_results': similar_videos
        })

