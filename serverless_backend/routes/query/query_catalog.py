from flask import Blueprint, jsonify
from firebase_admin import firestore
from datetime import datetime
from serverless_backend.services.firebase import FirebaseService
from serverless_backend.services.langchain_chains.wyr.generate_options import generate_options
from serverless_backend.services.open_ai import OpenAIService
from serverless_backend.services.vector_db.ziliz import ZilizVectorDB

query_catalog = Blueprint("query_catalog", __name__)


@query_catalog.route("/v1/query-data-catalog/<request_id>", methods=['GET'])
def perform_query_catalog(request_id):
    firebase_service = FirebaseService()
    ziliz_vector_db = ZilizVectorDB()
    open_ai_service = OpenAIService()

    try:
        request_doc = firebase_service.get_document("requests", request_id)
        if not request_doc:
            return jsonify({"status": "error", "message": "Request not found"}), 404

        query_id = request_doc.get('queryId')
        if not query_id:
            return jsonify({"status": "error", "message": "query ID not found in request"}), 400

        query_document = firebase_service.get_document("queries", query_id)
        if not query_document:
            return jsonify({"status": "error", "message": "Niche document not found"}), 404

        query_results = query_document.get('queryResults', 5)
        query_text = query_document['queryText']
        channel_filters = query_document.get('channelFilter', [])
        video_filters = query_document.get('videoFilter', [])

        if not query_text:
            return jsonify({"status": "error", "message": "No query text found"}), 404


        # Update request log to indicate process initiation
        firebase_service.update_document("requests", request_id, {
            "logs": firestore.firestore.ArrayUnion([{
                "message": f"Querying data catalog for: '{query_text}'",
                "timestamp": datetime.now()
            }])
        })

        def update_progress(progress):
            firebase_service.update_document("requests", request_id, {"progress": progress})

        def update_message(message):
            firebase_service.update_message(request_id, message)

        update_progress(0)

        # Generate embedding for the query text
        query_embedding = open_ai_service.get_embedding(query_text)
        if not query_embedding:
            raise ValueError("Failed to generate embedding for query text")

        firebase_service.update_document(
            'queries',
            query_id,
            {
                'status': 'started'
            }
        )

        update_progress(25)
        update_message("Query embedding generated")

        search_params = {
            "metric_type": "COSINE",
            "params": {"nprobe": 10}
        }

        filter_conditions = []
        if channel_filters:
            filter_conditions.append(f"channel_id in {channel_filters}")
        if video_filters:
            filter_conditions.append(f"video_id in {video_filters}")

        filter_expr = " and ".join(filter_conditions) if filter_conditions else ""

        results = ziliz_vector_db.client.search(
            collection_name="segments",
            data=[query_embedding],
            filter=filter_expr,
            limit=query_results,
            output_fields=["segments_id", "video_id", "channel_id"],
            search_params=search_params
        )

        formatted_results = []
        for hit in results[0]:
            formatted_results.append({
                "segment_id": hit['entity'].get("segments_id"),
                "distance": hit.get('distance'),
                "video_id": hit['entity'].get("video_id"),
                "channel_id": hit['entity'].get("channel_id")
            })

        firebase_service.update_document(
            'queries',
            query_id,
            {
            'embeddingValue': query_embedding,
            'filterResults': formatted_results,
            'queriedTime': datetime.now(),
            'status': 'complete'
            }
        )


        update_progress(100)
        update_message("Results processed successfully")

        return jsonify({
            "status": "success",
            "data": {
                "request_id": request_id,
                "query_id": query_id,
                "query_text": query_text,
                "results": formatted_results
            },
            "message": f"Successfully queried data catalog"
        }), 200

    except Exception as e:
        firebase_service.update_document(
            'queries',
            query_id,
            {
                'status': 'failed'
            }
        )
        return jsonify({
            "status": "error",
            "data": {
                "request_id": request_id,
                "error": str(e)
            },
            "message": "Failed to query catalog"
        }), 500