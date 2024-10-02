import os

from pymilvus import MilvusClient, DataType

from serverless_backend.services.open_ai import OpenAIService


class ZilizVectorDB:
    def __init__(self):
        self.cluster_endpoint = os.getenv('ZILIZ_CLUSTER_ENDPOINT')
        self.token = os.getenv('ZILIZ_CLUSTER_TOKEN')
        self.client = MilvusClient(
            uri=self.cluster_endpoint,
            token=self.token
        )

    def create_segments_collection(self):
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field(field_name="segments_id", datatype=DataType.VARCHAR, is_primary=True, max_length=30)
        schema.add_field(field_name="video_id", datatype=DataType.VARCHAR, max_length=30)
        schema.add_field(field_name="channel_id", datatype=DataType.VARCHAR, max_length=30)
        schema.add_field(field_name="textual_vector", datatype=DataType.FLOAT_VECTOR, dim=1536)

        index_params = MilvusClient.prepare_index_params()

        # 4.2. Add an index on the vector field.
        index_params.add_index(
            field_name="textual_vector",
            metric_type="COSINE",
            index_type="AUTOINDEX",
            index_name="vector_index"
        )

        self.client.create_collection(
            collection_name="segments",
            schema=schema,
            index_params=index_params
        )

    def insert_to_collection(self, collection_name, data):
        self.client.insert(collection_name=collection_name, data=data)

    def generate_segment_text(self, segment):
        return f"Segment Title: {segment['segment_title']} \n Segment Description: {segment['segment_summary']} \n Transcript: {segment['transcript']}"

    def get_embedding_and_upload_to_segments(self, text, segment_id, video_id, channel_id):
        open_ai = OpenAIService()
        embedding = open_ai.get_embedding(text)
        if embedding:
            self.insert_to_collection(
                'segments',
                data=[{
                    'segments_id': segment_id,
                    'textual_vector': embedding,
                    'video_id': video_id,
                    'channel_id': channel_id
                }]
            )