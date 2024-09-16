import io
import json

from flask import Blueprint, jsonify, request
from firebase_admin import firestore
from datetime import datetime
from serverless_backend.services.firebase import FirebaseService
import requests
import os

generate_images = Blueprint("generate_images", __name__)


@generate_images.route("/v1/generate-images/<image_id>", methods=['GET'])
def generate_images_endpoint(image_id):
    firebase_service = FirebaseService()

    try:
        # Generate a unique image_id
        image = firebase_service.get_document('images', image_id)
        prompt = image.get('prompt')
        setup = image.get('setup', 'square')  # Default to square if not specified
        num_generations = image.get('num_generations', 1)  # Default to 1 if not specified

        if not prompt:
            return jsonify({"status": "error", "message": "Prompt is required"}), 400

        # Update request log to indicate process initiation
        firebase_service.update_document("images", image_id, {
            "status": "processing",
            "prompt": prompt,
            "setup": setup,
            "num_generations": num_generations,
            "created_at": firestore.firestore.SERVER_TIMESTAMP
        })

        # Prepare the request payload for Beam API
        payload = {
            "prompt": prompt,
            "setup": setup,
            "num_generations": num_generations
        }

        response = requests.post(
            os.getenv('IMAGE_GENERATOR_ENDPOINT'),
            headers={
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate",
                "Authorization": "Bearer " + os.getenv("SALIENCY_BEARER_TOKEN") + "==",
                "Connection": "keep-alive",
                "Content-Type": "application/json"
            },
            data=json.dumps(payload)
        )

        if response.status_code == 200:
            result = response.json()
            image_urls = result.get('images', [])

            firebase_image_paths = []
            for i, image_url in enumerate(image_urls):
                image_response = requests.get(image_url)
                if image_response.status_code == 200:
                    blob_path = f'generated_images/{image_id}/image_{i + 1}.png'
                    # Pass the content directly, no need for BytesIO
                    firebase_service.upload_file_from_memory(image_response.content, blob_path)
                    firebase_image_paths.append(blob_path)

            # Update the document with the generated image paths
            firebase_service.update_document("images", image_id, {
                "status": "completed",
                "image_paths": firebase_image_paths,
                "completed_at": firestore.firestore.SERVER_TIMESTAMP
            })

            return jsonify({
                "status": "success",
                "data": {
                    "image_id": image_id,
                    "image_paths": firebase_image_paths
                },
                "message": "Successfully generated images."
            }), 200
        else:
            raise Exception(f"Beam API request failed with status code: {response.status_code}")

    except Exception as e:
        # Update the document with error status
        firebase_service.update_document("images", image_id, {
            "status": "error",
            "error_message": str(e),
            "completed_at": firestore.firestore.SERVER_TIMESTAMP
        })
        return jsonify({
            "status": "error",
            "data": {
                "image_id": image_id,
                "error": str(e)
            },
            "message": "Failed to generate images"
        }), 500