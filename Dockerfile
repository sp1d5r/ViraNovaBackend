# Use an official Python runtime as a base image
FROM python:3.8-slim

# Set the working directory in the container to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
# Including Gunicorn, Firebase Admin SDK, Google Cloud Text-to-Speech, OpenAI, and Flask
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install gunicorn firebase-admin google-cloud-texttospeech openai Flask

# Install FFMPEG
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Get environment vars
# Google Keys
ARG SERVICE_ACCOUNT_ENCODED
ENV SERVICE_ACCOUNT_ENCODED=${SERVICE_ACCOUNT_ENCODED}
ARG FIREBASE_STORAGE_BUCKET
ENV FIREBASE_STORAGE_BUCKET=${FIREBASE_STORAGE_BUCKET}

# Open AI Keys
ARG OPENAI_API_KEY
ENV OPENAI_API_KEY=${OPENAI_API_KEY}

# Postgres Database
ARG POSTGRES_USER
ENV POSTGRES_USER=${POSTGRES_USER}
ARG POSTGRES_PASSWORD
ENV POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
ARG POSTGRES_HOST
ENV POSTGRES_HOST=${POSTGRES_HOST}
ARG POSTGRES_PORT
ENV POSTGRES_PORT=${POSTGRES_PORT}
ARG POSTGRES_DATABASE
ENV POSTGRES_DATABASE=${POSTGRES_DATABASE}
ARG POSTGRES_SSLMODE
ENV POSTGRES_SSLMODE=${POSTGRES_SSLMODE}

# QDRANT Vector DB
ARG QDRANT_LOCATION
ENV QDRANT_LOCATION=${QDRANT_LOCATION}

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variable to specify the Flask application
ENV FLASK_APP=app.py

# Use Gunicorn to serve the Flask app. Adjust the number of workers and threads as necessary.
# Replace 'app:app' with 'your_flask_app_module:app' if your application's instance is named differently
CMD ["gunicorn", "-b", "0.0.0.0:5000", "--timeout", "1800", "app:app"]
