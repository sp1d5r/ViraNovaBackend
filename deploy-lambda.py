import boto3
import botocore
import docker
import time
import json
import base64
import hashlib
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
aws_region = 'eu-west-2'
repository_name = 'viranova-serverless-repo'
lambda_function_name = 'viranova-backend-lambda'
dockerfile_path = 'Dockerfile'  # Path to your Dockerfile.prod
app_name = 'serverless_backend.app.lambda_handler'  # Your Lambda handler
api_name = 'viranova-api'
stage_name = 'prod'

# Initialize boto3 clients
ecr_client = boto3.client('ecr', region_name=aws_region)
lambda_client = boto3.client('lambda', region_name=aws_region)
iam_client = boto3.client('iam')
apigateway_client = boto3.client('apigateway', region_name=aws_region)

# Initialize Docker client
docker_client = docker.from_env()

# Step 1: Create ECR repository if it doesn't exist
def create_ecr_repository(repository_name):
    try:
        response = ecr_client.create_repository(repositoryName=repository_name)
        repository_uri = response['repository']['repositoryUri']
        print(f'Repository created: {repository_uri}')
        return repository_uri
    except ecr_client.exceptions.RepositoryAlreadyExistsException:
        response = ecr_client.describe_repositories(repositoryNames=[repository_name])
        repository_uri = response['repositories'][0]['repositoryUri']
        print(f'Repository exists: {repository_uri}')
        return repository_uri

# Step 2: Build Docker image
import os
import docker

def build_docker_image(repository_uri, dockerfile_path="Dockerfile"):
    env_vars = {
        "FIREBASE_STORAGE_BUCKET": os.getenv("FIREBASE_STORAGE_BUCKET"),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "OPEN_AI_KEY_OLD": os.getenv("OPEN_AI_KEY_OLD"),
        "SERVICE_ACCOUNT_ENCODED": os.getenv("SERVICE_ACCOUNT_ENCODED"),
        "BACKEND_SERVICE_ADDRESS": os.getenv("BACKEND_SERVICE_ADDRESS"),
        "VIDEO_DOWNLOAD_LOCATION": os.getenv("VIDEO_DOWNLOAD_LOCATION"),
        "AUDIO_DOWNLOAD_LOCATION": os.getenv("AUDIO_DOWNLOAD_LOCATION"),
        "POSTGRES_USER": os.getenv("POSTGRES_USER"),
        "POSTGRES_PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "POSTGRES_HOST": os.getenv("POSTGRES_HOST"),
        "POSTGRES_PORT": os.getenv("POSTGRES_PORT"),
        "POSTGRES_DATABASE": os.getenv("POSTGRES_DATABASE"),
        "POSTGRES_SSLMODE": os.getenv("POSTGRES_SSLMODE"),
        "QDRANT_LOCATION": os.getenv("QDRANT_LOCATION"),
        "LANGCHAIN_TRACING_V2": os.getenv("LANGCHAIN_TRACING_V2"),
        "LANGCHAIN_API_KEY": os.getenv("LANGCHAIN_API_KEY"),
        "LANGCHAIN_PROJECT": os.getenv("LANGCHAIN_PROJECT"),
        "NUM_CPU_CORES": os.getenv("NUM_CPU_CORES"),
        "SECRET_KEY": os.getenv("SECRET_KEY"),
        "SALIENCY_BEARER_TOKEN": os.getenv("SALIENCY_BEARER_TOKEN"),
        "SALIENCY_ENDPOINT_ADDRESS": os.getenv("SALIENCY_ENDPOINT_ADDRESS")
    }
    build_args = {k: v for k, v in env_vars.items() if v is not None}

    try:
        client = docker.from_env()
        # Build the image
        image, build_logs = client.images.build(
            path=".",
            dockerfile=dockerfile_path,
            buildargs=build_args,
            cache_from=[repository_uri]  # Use the cache from the existing image if available
        )
        for log in build_logs:
            if 'stream' in log:
                print(log['stream'].strip())
            if 'error' in log:
                print(log['error'].strip())
                raise Exception(log['error'].strip())
        print(f'Docker image built: {image.tags}')

        # Tag the image with the repository URI
        image.tag(repository_uri, tag='latest')

        # Push the image to the repository
        response = client.images.push(repository_uri, tag='latest')
        print(f'Docker image pushed: {repository_uri}')
        print(response)

        return image
    except docker.errors.BuildError as e:
        print(f"Docker build failed: {str(e)}")
        for log in e.build_log:
            if 'stream' in log:
                print(log['stream'].strip())
            if 'error' in log:
                print(log['error'].strip())
        raise
    except docker.errors.APIError as e:
        print(f"Docker push failed: {str(e)}")
        raise


# Calculate the digest of the local Docker image
def calculate_local_image_digest(image):
    image_inspect = docker_client.api.inspect_image(image.id)
    image_config = json.dumps(image_inspect['ContainerConfig'], sort_keys=True)
    return hashlib.sha256(image_config.encode('utf-8')).hexdigest()

# Step 3: Check if image exists in ECR
def image_exists_in_ecr(repository_uri):
    try:
        response = ecr_client.describe_images(repositoryName=repository_name, imageIds=[{'imageTag': 'latest'}])
        image_digest = response['imageDetails'][0]['imageDigest']
        return image_digest
    except ecr_client.exceptions.ImageNotFoundException:
        return None

# Step 4: Push Docker image to ECR
def push_docker_image(repository_uri):
    auth_token_response = ecr_client.get_authorization_token()
    auth_data = auth_token_response['authorizationData'][0]
    token = base64.b64decode(auth_data['authorizationToken']).decode('utf-8')
    username, password = token.split(':')

    registry = auth_data['proxyEndpoint']

    login_response = docker_client.login(username=username, password=password, registry=registry)
    print(f"Login response: {login_response}")

    push_logs = docker_client.images.push(repository_uri, tag='latest', stream=True, decode=True)
    for log in push_logs:
        if 'status' in log:
            print(log['status'])
        if 'errorDetail' in log:
            print(log['errorDetail'])
            raise Exception("Failed to push Docker image to ECR")

# Step 5: Create or update Lambda function
def create_or_update_lambda_function(repository_uri, lambda_function_name, role_arn):
    try:
        response = lambda_client.update_function_code(
            FunctionName=lambda_function_name,
            ImageUri=f"{repository_uri}:latest",
            Publish=True
        )
        print(f'Updated Lambda function code: {lambda_function_name}')
    except lambda_client.exceptions.ResourceNotFoundException:
        # Create the function if it doesn't exist
        response = lambda_client.create_function(
            FunctionName=lambda_function_name,
            Role=role_arn,
            Code={
                'ImageUri': f"{repository_uri}:latest"
            },
            Publish=True,
            PackageType='Image',
        )
        print(f'Created Lambda function: {lambda_function_name}')
    return response

# Get role ARN
def get_lambda_execution_role():
    role_name = 'lambda-execution-role'
    try:
        role = iam_client.get_role(RoleName=role_name)
    except iam_client.exceptions.NoSuchEntityException:
        assume_role_policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "lambda.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        role = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy_document)
        )
        iam_client.attach_role_policy(
            RoleName=role_name,
            PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
        )
        time.sleep(10)  # Wait for the role to propagate
    return role['Role']['Arn']

# Create API Gateway and link it to the Lambda function
def get_resource_id(api_id, parent_id, path_part):
    resources = apigateway_client.get_resources(restApiId=api_id)
    for resource in resources['items']:
        if 'parentId' in resource and resource['parentId'] == parent_id and resource['pathPart'] == path_part:
            return resource['id']
    return None

def create_api_gateway(lambda_function_name, api_name, stage_name, routes):
    # Create the API
    api_response = apigateway_client.create_rest_api(
        name=api_name,
        description='API for ViraNova Lambda function',
        endpointConfiguration={
            'types': ['REGIONAL']
        }
    )
    api_id = api_response['id']
    print(f'Created API Gateway: {api_name} with ID: {api_id}')

    # Get the root resource ID
    resources = apigateway_client.get_resources(restApiId=api_id)
    root_id = [resource['id'] for resource in resources['items'] if resource['path'] == '/'][0]

    for route, methods in routes:
        print(f"Processing route: {route}")
        path_parts = route.lstrip('/').split('/')
        path_parts = [part for part in path_parts if part]  # Remove empty parts

        parent_id = root_id
        for part in path_parts:
            if part.startswith('<') and part.endswith('>'):
                part = '{' + part[1:-1] + '}'

            if not part:  # Ensure part is not empty
                raise ValueError(f"Invalid path part: {part}")

            print(f"Creating resource for part: {part} under parent ID: {parent_id}")
            # Check if the resource already exists
            resource_id = get_resource_id(api_id, parent_id, part)
            if resource_id:
                parent_id = resource_id
                print(f'Resource for {part} already exists with ID: {parent_id}')
            else:
                try:
                    resource_response = apigateway_client.create_resource(
                        restApiId=api_id,
                        parentId=parent_id,
                        pathPart=part
                    )
                    parent_id = resource_response['id']
                    print(f'Created resource for {part} with ID: {parent_id}')
                except botocore.exceptions.ClientError as e:
                    print(f"Error creating resource for {part}: {e}")
                    raise

        for method in methods.split(','):
            if method not in ['HEAD', 'OPTIONS']:  # Skip unsupported methods
                print(f"Creating {method} method on {route} with parent ID: {parent_id}")
                try:
                    method_response = apigateway_client.put_method(
                        restApiId=api_id,
                        resourceId=parent_id,
                        httpMethod=method,
                        authorizationType='NONE'
                    )
                    print(f'Created {method} method on {route}')

                    apigateway_client.put_integration(
                        restApiId=api_id,
                        resourceId=parent_id,
                        httpMethod=method,
                        type='AWS_PROXY',
                        integrationHttpMethod='POST',
                        uri=f'arn:aws:apigateway:{aws_region}:lambda:path/2015-03-31/functions/arn:aws:lambda:{aws_region}:{boto3.client("sts").get_caller_identity()["Account"]}:function:{lambda_function_name}/invocations'
                    )
                    print(f'Linked {method} method to Lambda function')
                except botocore.exceptions.ClientError as e:
                    print(f"Error creating method {method} for {route}: {e}")
                    raise

    # Deploy the API
    deployment_response = apigateway_client.create_deployment(
        restApiId=api_id,
        stageName=stage_name
    )
    print(f'Deployed API to stage: {stage_name}')

    invoke_url = f'https://{api_id}.execute-api.{aws_region}.amazonaws.com/{stage_name}'
    print(f'API Gateway URL: {invoke_url}')
    return invoke_url, api_id

# Adding permission to the lambda function
def add_permission_to_lambda(lambda_function_name, api_id):
    lambda_client.add_permission(
        FunctionName=lambda_function_name,
        StatementId='apigateway-access',
        Action='lambda:InvokeFunction',
        Principal='apigateway.amazonaws.com',
        SourceArn=f'arn:aws:execute-api:{aws_region}:{boto3.client("sts").get_caller_identity()["Account"]}:{api_id}/*/GET/v1/split-video/*'
    )
    print(f'Added permission for API Gateway to invoke Lambda function {lambda_function_name}')

# Main script execution
def main():
    repository_uri = create_ecr_repository(repository_name)
    image = build_docker_image(repository_uri)

    local_digest = calculate_local_image_digest(image)
    remote_digest = image_exists_in_ecr(repository_uri)

    if local_digest == remote_digest:
        print("Local image is up-to-date with the ECR image. No need to push.")
    else:
        push_docker_image(repository_uri)

    role_arn = get_lambda_execution_role()
    create_or_update_lambda_function(repository_uri, lambda_function_name, role_arn)

    # List routes in the Flask app
    from serverless_backend.app import app, list_routes
    routes = list_routes(app)

    api_gateway_url, api_id = create_api_gateway(lambda_function_name, api_name, stage_name, routes)
    print(f'Your Lambda function can be called at: {api_gateway_url}')
    add_permission_to_lambda(lambda_function_name, api_id)

if __name__ == '__main__':
    main()
