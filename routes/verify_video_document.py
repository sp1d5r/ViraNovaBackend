
def parse_and_verify_video(video_document: dict) -> (bool, str):
    if not video_document:
        return False, "Document Not found"

    # Define the required keys and their expected types
    required_keys = {
        "originalFileName": str,
        "processingProgress": int,
        "queuePosition": int,
        "status": str,
        "uid": str,
        "uploadTimestamp": int,
        "videoPath": str,
    }

    # Check for missing keys
    missing_keys = [key for key in required_keys if key not in video_document]
    if missing_keys:
        return False, f"Missing keys: {', '.join(missing_keys)}"

    # Check for keys with incorrect type
    incorrect_type_keys = [key for key, expected_type in required_keys.items()
                           if not isinstance(video_document.get(key), expected_type)]
    # if incorrect_type_keys:
    #     return False, f"Keys with incorrect type: {', '.join(incorrect_type_keys)}"

    return True, "Document is valid."