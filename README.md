# ViraNova Backend

## Contents 
* Viranova Backend API - Uses Flask to set up API endpoints for frontend to interact with. Handles tasks user will need as 
video flows through transformation by transformation
* Viranova Cloud Functions - Handles tracking document change and triggers requests to work queue.

---

# Viranova Backend API

## Overview

This Flask application serves as the backend for the Viranova application. It provides various routes for processing 
and managing video content, including splitting videos into audio and video components, transcribing and diarizing 
audio, extracting topical segments, summarizing segments, and retrieving random videos.


These endpoints are split between google-function end-points and endpoints for the frontend. Majority of these 
get placed in a google queue for longer processing. 

## Routes and Functionality

`/split-video/<video_id>`

- **Description:** Splits the provided video into audio and video components.
- **Parameters:**
  - `video_id`: The unique identifier of the video to be split.
- **Returns:** Returns a message indicating the status of the split process.

`/transcribe-and-diarize/<video_id>`

- **Description:** Transcribes and diarizes the audio of the provided video.
- **Parameters:**
  - `video_id`: The unique identifier of the video to be transcribed and diarized.
- **Returns:** Returns the transcribed content and word data.

`/extract-topical-segments/<video_id>`

- **Description:** Extracts topical segments from the provided video.
- **Parameters:**
  - `video_id`: The unique identifier of the video to extract segments from.
- **Returns:** Returns the extracted segments.

`/summarise-segments/<video_id>`

- **Description:** Summarizes the extracted topical segments of the provided video.
- **Parameters:**
  - `video_id`: The unique identifier of the video to summarize segments for.
- **Returns:** Returns the summarized segments.

`/get-random-video`

- **Description:** Retrieves a random video from the video directory.
- **Returns:** Returns the filename of a randomly selected video.

`/load-segmentation-from-file/<video_file>/`

- **Description:** Loads segmentation masks from a specified video file.
- **Parameters:**
  - `video_file`: The filename of the video to load segmentation masks from.
- **Returns:** Returns the segmentation masks for the specified video file.

`/v2/get-random-short-video`

- **Description:** Retrieves a random short video from the database.
- **Returns:** Returns the video ID of a randomly selected short video.

`/v2/get-short-and-segments`

- **Description:** Retrieves short videos and their related segments from the vector database.
- **Returns:** Returns information about related short videos and segments.

`/`

- **Description:** Default route.
- **Returns:** Returns a message indicating the backend is running.
