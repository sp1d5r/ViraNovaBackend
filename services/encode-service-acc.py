import base64

# Replace 'path/to/your/service-account-file.json' with the path to your JSON file
file_path = '../viranova-firebase-service-account.json'

with open(file_path, 'r') as json_file:
    json_str = json_file.read()

# Encode the JSON string to Base64 to make it safe for environment variables
encoded_json_str = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')

print(encoded_json_str)
