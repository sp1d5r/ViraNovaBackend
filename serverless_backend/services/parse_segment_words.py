import json
import ast

def fix_string_representation(input_string):
    # Check if the string starts with a double quote
    if input_string.startswith('"'):
        # Remove the extra quotes at the beginning and end
        cleaned_string = input_string.strip('"')

        # Replace escaped single quotes with double quotes
        cleaned_string = cleaned_string.replace("\\'", '"')

        # Remove backslashes before double quotes
        cleaned_string = cleaned_string.replace('\\"', '"')

        try:
            # Try to parse as JSON
            return json.loads(cleaned_string)
        except json.JSONDecodeError:
            # If JSON parsing fails, fall back to ast.literal_eval
            return ast.literal_eval(cleaned_string)
    else:
        # If it doesn't start with a double quote, use ast.literal_eval directly
        return ast.literal_eval(input_string)


def parse_segment_words(segment_document):
    try:
        return fix_string_representation(segment_document['words'])
    except (ValueError, SyntaxError, json.JSONDecodeError) as e:
        print(f"Error parsing segment words: {e}")
        print(f"Problematic string: {segment_document['words'][:100]}...")  # Print first 100 chars for debugging
        raise ValueError(f"Failed to parse segment words: {e}")
