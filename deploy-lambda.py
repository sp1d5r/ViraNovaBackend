import boto3
import botocore
from botocore.exceptions import ClientError
import docker
import time
import json
import base64
import hashlib
import random
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
aws_region = 'eu-west-2'
repository_name = 'viranova-serverless-repo'
lambda_function_name = 'viranova-backend-lambda'
dockerfile_path = 'Dockerfile.prod'  # Path to your Dockerfile.prod
app_name = 'serverless_backend.app.lambda_handler'  # Your Lambda handler
api_name = 'viranova-api'
stage_name = 'prod'

# Initialize boto3 clients
ecr_client = boto3.client('ecr', region_name=aws_region)
lambda_client = boto3.client('lambda', region_name=aws_region)
iam_client = boto3.client('iam')
apigateway_client = boto3.client('apigateway', region_name=aws_region)
account_id = boto3.client("sts").get_caller_identity()["Account"]

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
        "SALIENCY_ENDPOINT_ADDRESS": os.getenv("SALIENCY_ENDPOINT_ADDRESS"),
        "APIFY_TOKEN": os.getenv("APIFY_TOKEN"),
        "YOUTUBE_API_KEY": os.getenv("YOUTUBE_API_KEY"),
        "BREVO_API_KEY": os.getenv("BREVO_API_KEY"),
        "DEEP_GRAM_API_KEY": os.getenv("DEEP_GRAM_API_KEY"),
        "ELEVENLABS_API_KEY": os.getenv("ELEVENLABS_API_KEY"),
        "BEAM_BEARER_TOKEN": os.getenv("BEAM_BEARER_TOKEN"),
        "IMAGE_GENERATOR_ENDPOINT": os.getenv("IMAGE_GENERATOR_ENDPOINT"),
        "ZILIZ_CLUSTER_TOKEN": os.getenv('ZILIZ_CLUSTER_TOKEN'),
        "ZILIZ_CLUSTER_ENDPOINT": os.getenv('ZILIZ_CLUSTER_ENDPOINT')
    }
    build_args = {k: v for k, v in env_vars.items() if v is not None}

    try:
        client = docker.from_env()
        # Build the image
        image, build_logs = client.images.build(
            path=".",
            dockerfile=dockerfile_path,
            buildargs=build_args,
            platform="linux/amd64",
        )
        for log in build_logs:
            if 'stream' in log:
                print(log['stream'].strip())
            if 'error' in log:
                print(log['error'].strip())
                raise Exception(log['error'].strip())

        # Tag the image with the repository URI
        image.tag(repository_uri, tag='latest')
        print(f'Docker image built: {image.tags}')

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


def delete_resource(api_id, resource_id):
    try:
        apigateway_client.delete_resource(
            restApiId=api_id,
            resourceId=resource_id
        )
        print(f"Deleted resource with ID: {resource_id}")
    except Exception as e:
        print(f"Error deleting resource: {str(e)}")

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

def get_existing_api_id(api_name):
    try:
        apis = apigateway_client.get_rest_apis()
        existing_apis = [api for api in apis['items'] if api['name'] == api_name]
        if existing_apis:
            # Sort by creation date and get the most recent one
            existing_apis.sort(key=lambda x: x['createdDate'], reverse=True)
            return existing_apis[0]['id']
    except botocore.exceptions.ClientError as e:
        print(f"Error getting existing APIs: {e}")
    return None


# Create API Gateway and link it to the Lambda function
def get_resource_id(api_id, parent_id, path_part):
    try:
        resources = apigateway_client.get_resources(restApiId=api_id, limit=500)
        for resource in resources['items']:
            if resource.get('parentId') == parent_id and resource.get('pathPart') == path_part:
                print(f"Resource {path_part} already exists under parent {parent_id} with ID: {resource['id']}")
                return resource['id']
    except Exception as e:
        print(f"Error retrieving resource ID for {path_part}: {str(e)}")
    print(f"No existing resource found for {path_part} under parent {parent_id}")
    return None


# Step 6) Update the API gateway
def create_or_update_api_gateway(lambda_function_name, api_name, stage_name, routes):
    api_id = get_existing_api_id(api_name)
    if api_id:
        print(f"API Gateway {api_name} already exists with ID: {api_id}")
    else:
        api_response = apigateway_client.create_rest_api(
            name=api_name,
            description='API for ViraNova Lambda function',
            endpointConfiguration={'types': ['REGIONAL']}
        )
        api_id = api_response['id']
        print(f'Created API Gateway: {api_name} with ID: {api_id}')

    resources = apigateway_client.get_resources(restApiId=api_id, limit=500)
    root_resource = next((resource for resource in resources['items'] if 'parentId' not in resource), None)
    if root_resource is None:
        print("Root resource ID not found")
        return None, None
    root_id = root_resource['id']
    print(f"Root resource ID found: {root_id}")

    valid_methods = ['GET', 'POST']

    for route, methods in routes:
        path_parts = route.strip('/').split('/')
        current_parent_id = root_id

        for part in path_parts:
            if part.startswith('<') and part.endswith('>'):
                part = '{' + part[1:-1] + '}'
            if not part.strip():  # Skip empty path parts
                continue

            # Check for existing {short_id} resource and delete it
            existing_short_id_resource = get_resource_id(api_id, current_parent_id, '{short_id}')
            if existing_short_id_resource:
                delete_resource(api_id, existing_short_id_resource)
                print(f"Deleted existing {{short_id}} resource")

            resource_id = get_resource_id(api_id, current_parent_id, part)
            if not resource_id:
                try:
                    resource_response = apigateway_client.create_resource(
                        restApiId=api_id,
                        parentId=current_parent_id,
                        pathPart=part
                    )
                    resource_id = resource_response['id']
                    print(f"Created new resource for {part} with ID: {resource_id}")
                except Exception as e:
                    print(f"Failed to create resource {part}: {str(e)}")
                    continue
            current_parent_id = resource_id

        methods_to_setup = [method for method in methods.split(',') if method in valid_methods]
        for method in methods_to_setup:
            try:
                # Check if the method already exists
                apigateway_client.get_method(
                    restApiId=api_id,
                    resourceId=current_parent_id,
                    httpMethod=method
                )
                # If method exists, delete it before recreating it
                apigateway_client.delete_method(
                    restApiId=api_id,
                    resourceId=current_parent_id,
                    httpMethod=method
                )
                print(f"Deleted existing {method} method on {route}")
            except:
                print(f"No existing {method} method on {route}, creating new one")

            apigateway_client.put_method(
                restApiId=api_id,
                resourceId=current_parent_id,
                httpMethod=method,
                authorizationType='NONE',
                requestParameters={'method.request.header.X-Auth-Token': True}
            )
            print(f"Set up {method} method on {route}")

            apigateway_client.put_integration(
                restApiId=api_id,
                resourceId=current_parent_id,
                httpMethod=method,
                type='AWS_PROXY',
                integrationHttpMethod='POST',
                timeoutInMillis=29000,
                uri=f'arn:aws:apigateway:{aws_region}:lambda:path/2015-03-31/functions/arn:aws:lambda:{aws_region}:{account_id}:function:{lambda_function_name}/invocations',
                requestParameters={
                    'integration.request.header.X-Auth-Token': 'method.request.header.X-Auth-Token'
                }
            )
            print(f"Set up integration for {method} method on {route}, with timeout of 29000")

    deployment_response = apigateway_client.create_deployment(
        restApiId=api_id,
        stageName=stage_name
    )
    print(f"Deployed API to stage: {stage_name}")
    invoke_url = f'https://{api_id}.execute-api.{aws_region}.amazonaws.com/{stage_name}'
    print(f"API Gateway URL: {invoke_url}")

    return invoke_url, api_id

def remove_existing_permissions():
    try:
        # Remove the existing permissions if they exist
        lambda_client.remove_permission(
            FunctionName=lambda_function_name,
            StatementId='apigateway-access'
        )
        print(f'Removed existing permission with StatementId apigateway-access')
    except lambda_client.exceptions.ResourceNotFoundException:
        pass  # Permission did not exist, continue


def add_permission_to_lambda(api_id):
    for method in ['GET', 'POST']:  # Add other methods if needed
        source_arn = f'arn:aws:execute-api:{aws_region}:{account_id}:{api_id}/*/{method}/*'
        try:
            lambda_client.add_permission(
                FunctionName=lambda_function_name,
                StatementId=f'apigateway-access-{method.lower()}',
                Action='lambda:InvokeFunction',
                Principal='apigateway.amazonaws.com',
                SourceArn=source_arn
            )
            print(f'Added permission for API Gateway to invoke Lambda function {lambda_function_name} for {method} requests')
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'ResourceConflictException':
                print(f'Permission already exists for {method} requests')
            else:
                print(f"Error adding permission for {method} requests: {e}")
                raise

def verify_api_gateway_integration(api_id, lambda_function_name):
    resources = apigateway_client.get_resources(restApiId=api_id)
    for resource in resources['items']:
        if 'resourceMethods' in resource:
            for method in ['GET', 'POST']:  # Add other methods if needed
                if method in resource['resourceMethods']:
                    integration = apigateway_client.get_integration(
                        restApiId=api_id,
                        resourceId=resource['id'],
                        httpMethod=method
                    )
                    expected_uri = f'arn:aws:apigateway:{aws_region}:lambda:path/2015-03-31/functions/arn:aws:lambda:{aws_region}:{account_id}:function:{lambda_function_name}/invocations'
                    if integration['uri'] != expected_uri:
                        print(f"Updating integration for {method} method on resource {resource['path']}")
                        apigateway_client.put_integration(
                            restApiId=api_id,
                            resourceId=resource['id'],
                            httpMethod=method,
                            type='AWS_PROXY',
                            integrationHttpMethod='POST',
                            uri=expected_uri
                        )
                        print(f"Updated integration for {method} method on resource {resource['path']}")


def deploy_api_gateway(api_id, stage_name, max_retries=5, initial_delay=1):
    retries = 0
    while retries < max_retries:
        try:
            deployment_response = apigateway_client.create_deployment(
                restApiId=api_id,
                stageName=stage_name
            )
            print(f'Deployed API to stage: {stage_name}')
            return deployment_response
        except ClientError as e:
            if e.response['Error']['Code'] == 'TooManyRequestsException':
                wait_time = (2 ** retries) * initial_delay + random.uniform(0, 1)
                print(f"Rate limited. Retrying in {wait_time:.2f} seconds...")
                time.sleep(wait_time)
                retries += 1
            else:
                print(f"Error deploying API: {e}")
                raise
    print(f"Failed to deploy API after {max_retries} attempts")
    raise Exception("Max retries exceeded for API deployment")

def update_lambda_permissions_and_deploy():
    api_id = get_existing_api_id(api_name)
    if api_id:
        remove_existing_permissions()
        add_permission_to_lambda(api_id)
        verify_api_gateway_integration(api_id, lambda_function_name)
        deploy_api_gateway(api_id, stage_name)
    else:
        print(f"API Gateway {api_name} not found.")



# Main script execution
def main():
    # Ensure your region is correctly set
    print(f"Current region: {boto3.Session().region_name}")

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
    from serverless_backend.main import app, list_routes
    routes = list_routes(app)
    print(routes)

    api_gateway_url, api_id = create_or_update_api_gateway(lambda_function_name, api_name, stage_name, routes)
    print(f'Your Lambda function can be called at: {api_gateway_url}')
    update_lambda_permissions_and_deploy()

if __name__ == '__main__':
    main()
