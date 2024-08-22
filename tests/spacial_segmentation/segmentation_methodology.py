import cv2
from serverless_backend.services.add_text_to_video_service import AddTextToVideoService
from serverless_backend.services.firebase import FirebaseService


def test_frame_processing():
    # Initialize the service
    service = AddTextToVideoService()
    firebase_service = FirebaseService()

    service.font_base_path = "/Users/elijahahmad/PycharmProjects/ViraNovaBackend/serverless_backend/assets/fonts/"

    # Load a sample frame (you can replace this with any image)
    frame = cv2.imread('sample.png')
    if frame is None:
        raise ValueError("Error: Could not load the sample frame.")

    height, width = frame.shape[:2]

    # Define colors (you can adjust these as needed)
    PRIMARY_COLOUR = (0, 255, 0)  # Green
    SECONDARY_COLOUR = (192, 255, 189)  # Light green
    LOGO = "ViraNova"

    user_id = "T7NdGmwlMwaZ5xLc0xN0BTl7hYH2"
    if user_id:
        user_doc = firebase_service.get_document("users", user_id)
        if user_doc:
            if 'channelName' in user_doc.keys():
                LOGO = user_doc['channelName']
            if 'primaryColor' in user_doc.keys():
                PRIMARY_COLOUR = tuple(int(user_doc['primaryColor'].lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
            if 'secondaryColor' in user_doc.keys():
                SECONDARY_COLOUR = tuple(int(user_doc['secondaryColor'].lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))

    # Prepare text additions
    text_additions = []

    # Add top title
    text_additions.append({
        'text': "TOP TITLE TEXT".upper(),
        'font_scale': 2,
        'thickness': 'Bold',
        'color': (255, 255, 255),
        'shadow_color': (0, 0, 0),
        'shadow_offset': (1, 1),
        'outline': True,
        'outline_color': (0, 0, 0),
        'outline_thickness': 3,
        'offset': (0, 0.15)
    })

    # Add bottom title
    text_additions.append({
        'text': "BOTTOM TITLE TEXT".upper(),
        'font_scale': 2,
        'thickness': 'Bold',
        'color': PRIMARY_COLOUR,
        'shadow_color': SECONDARY_COLOUR,
        'shadow_offset': (1, 1),
        'outline': True,
        'outline_color': SECONDARY_COLOUR,
        'outline_thickness': 2,
        'offset': (0, 0.17)
    })

    # Add logo
    text_additions.append({
        'text': LOGO,
        'font_scale': 1.7,
        'thickness': 'Bold',
        'color': PRIMARY_COLOUR,
        'shadow_color': (0, 0, 0),
        'shadow_offset': (1, 1),
        'outline': True,
        'outline_color': (0, 0, 0),
        'outline_thickness': 2,
        'offset': (0, 0.1)
    })

    # Add transcript
    text_additions.append({
        'type': 'transcript',
        'texts': ["TRANSCRIPT TRANSCRIPT TRANSCRIPT".lower()],
        'start_times': [0, 2],
        'end_times': [2, 4],
        'font_scale': 3,
        'thickness': 'Bold',
        'color': (255, 255, 255),
        'shadow_color': (0, 0, 0),
        'shadow_offset': (1, 1),
        'outline': True,
        'outline_color': (0, 0, 0),
        'outline_thickness': 4,
        'offset': (0, 0.05)
    })

    # Prepare fonts and positions for all text additions
    prepared_additions = []
    for addition in text_additions:
        if addition.get('type') == 'transcript':
            prepared_additions.extend(service._prepare_transcript(addition, width, height, 30))  # Assuming 30 fps
        else:
            prepared_additions.append(service._prepare_text_addition(addition, width, height))

    # Process the frame with all text additions
    for addition in prepared_additions:
        frame = service._process_frame(frame, addition['text'], addition['font'], addition['position'],
                                       addition['color'], addition['shadow_offset'],
                                       addition['shadow_color'], addition['outline'],
                                       addition['outline_color'], addition['outline_thickness'])

    # Save and display the result
    cv2.imwrite('output_frame.jpg', frame)
    cv2.imshow('Processed Frame', frame)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    test_frame_processing()