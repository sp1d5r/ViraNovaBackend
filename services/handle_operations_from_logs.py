def handle_operations_from_logs(logs, words):
    # Initialize all words with the position 'keep'
    for word in words:
        word['position'] = "keep"

    # Apply operations in the order they appear
    for log in logs:
        if log['type'] == "delete":
            for i in range(log['start_index'], log['end_index'] + 1):
                words[i]['position'] = 'delete'
        elif log['type'] == "undelete":
            for i in range(log['start_index'], log['end_index'] + 1):
                words[i]['position'] = 'keep'  # Restore to 'keep' if undeleted

    # Collect words to output that are not deleted
    output_words = [word for word in words if word['position'] == 'keep']

    return output_words