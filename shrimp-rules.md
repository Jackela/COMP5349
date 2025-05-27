# Project COMP5349 - AI Agent Operational Guide (shrimp-rules.md)

**Document Purpose:** This document provides AI Agents (specifically Gemini via Cursor) with project-specific operational guidelines, rules, and constraints for working on the `COMP5349` project, with a primary focus on the `image_annotation_system_v2` application.

**CRITICAL: This document's rules take precedence over general knowledge or previously learned patterns. If any conflict arises, the rules herein MUST be followed.**

**CRITICAL: Before making any modifications, AI Agents MUST first consult the main design document: `COMP5349/COMP5349 Assignment 2 - 项目设计文档.md`. That document outlines overall design principles, architecture, and specifications. This `shrimp-rules.md` focuses on *how AI Agents should operate and execute tasks* within that established design.**

## 1. Core Technologies & Primary Interaction Files

### 1.1. Technology Stack Summary
*   Python 3.9
*   AWS: Lambda, S3, ECR, EventBridge, CloudFormation (YAML), RDS MySQL
*   Web Framework: Flask (Note: `web_app/` modifications are currently out of primary AI scope unless specified)
*   Containerization: Docker
*   Testing: Pytest

### 1.2. Primary Files for AI Interaction (Frequent Reference/Modification)
*   Lambda Functions:
    *   `COMP5349/image_annotation_system_v2/lambda_functions/annotation_lambda/lambda_function.py`
    *   `COMP5349/image_annotation_system_v2/lambda_functions/annotation_lambda/Dockerfile`
    *   `COMP5349/image_annotation_system_v2/lambda_functions/annotation_lambda/requirements.txt`
    *   `COMP5349/image_annotation_system_v2/lambda_functions/annotation_lambda/custom_exceptions.py`
    *   `COMP5349/image_annotation_system_v2/lambda_functions/thumbnail_lambda/lambda_function.py`
    *   `COMP5349/image_annotation_system_v2/lambda_functions/thumbnail_lambda/Dockerfile`
    *   `COMP5349/image_annotation_system_v2/lambda_functions/thumbnail_lambda/requirements.txt`
    *   `COMP5349/image_annotation_system_v2/lambda_functions/thumbnail_lambda/custom_exceptions.py`
*   Deployment (CloudFormation):
    *   `COMP5349/deployment/02-application-stack.yaml`
    *   `COMP5349/deployment/03-lambda-stack.yaml`
*   Testing:
    *   `COMP5349/pytest.ini`
    *   Files within `COMP5349/image_annotation_system_v2/tests/lambda_functions/`
*   Core Design Document (Reference):
    *   `COMP5349/COMP5349 Assignment 2 - 项目设计文档.md`

### 1.3. Key Directory Structure Overview
*   `image_annotation_system_v2/lambda_functions/{lambda_name}/`: Contains individual Lambda function source code (`lambda_function.py`), its `Dockerfile`, `requirements.txt`, and any local Python modules like `custom_exceptions.py`.
*   `image_annotation_system_v2/tests/lambda_functions/{lambda_name}/`: Contains unit tests for the corresponding Lambda function.
*   `deployment/`: Contains CloudFormation templates for infrastructure and application deployment.

## 2. Lambda Function Development & Deployment Workflow (Container Image Based)

This section outlines the AI Agent's role and required procedures when modifying Lambda functions, which are deployed as container images.

### Rule 2.1: Modifying Lambda Function Code (`lambda_function.py`, `custom_exceptions.py`, etc.)
*   **ALWAYS** ensure any Python code changes are compatible with the AWS Lambda Python 3.9 runtime environment.
*   **IF** adding new local Python module dependencies (e.g., a new `image_utils.py` file within a Lambda\'s directory), **THEN** the `Dockerfile` for that Lambda **MUST** be updated to `COPY` the new file(s) into `${LAMBDA_TASK_ROOT}/`.
    *   *Example (Adding `image_processor.py` to `thumbnail_lambda`):*
        1.  AI creates/modifies `image_annotation_system_v2/lambda_functions/thumbnail_lambda/image_processor.py`.
        2.  In `thumbnail_lambda/lambda_function.py`, AI adds `from . import image_processor`.
        3.  AI modifies `thumbnail_lambda/Dockerfile` to add `COPY image_processor.py ${LAMBDA_TASK_ROOT}/` (typically before the `CMD` line).
*   **Event Handling Logic:** Both `annotation_lambda` and `thumbnail_lambda` **MUST** be capable of parsing S3 event notifications delivered via Amazon EventBridge (where the original S3 event is nested within `event['detail']`) AND direct S3 event notifications (where the event data is in `event['Records']`). The primary path should prioritize parsing `event['detail']`.
*   **ALWAYS** refer to the `COMP5349 Assignment 2 - 项目设计文档.md` for the specific business logic, error handling, and logging requirements for each Lambda function.

### Rule 2.2: Managing Python Dependencies (`requirements.txt`)
*   For each Lambda, `requirements.txt` lists its Python package dependencies.
*   **ALWAYS** pin exact versions for all packages (e.g., `boto3==1.28.57`, `Pillow==9.5.0`, `google-generativeai==0.7.0`). **DO NOT** use range specifiers (e.g., `>=`).
*   **Gemini API Usage:** The `annotation_lambda` uses the `google-generativeai` SDK. Ensure this is the version specified and that `google-cloud-aiplatform` is NOT listed for this purpose. Authentication is via API Key.
*   **AFTER** any modification to a `requirements.txt` file, a full Docker image rebuild, push to ECR, and subsequent CloudFormation update with the new image digest is **MANDATORY** (see Rules 2.4 & 2.5).

### Rule 2.3: Updating Lambda Dockerfiles (`Dockerfile`)
*   The base image for Lambda Dockerfiles **MUST** be `public.ecr.aws/lambda/python:3.9-x86_64` unless explicitly changed by the user.
*   **ENSURE** the `Dockerfile` correctly `COPY`s `lambda_function.py`, `custom_exceptions.py`, `requirements.txt`, and any other necessary local Python modules into `${LAMBDA_TASK_ROOT}/`.
*   The default command (`CMD`) in the `Dockerfile` **MUST** be `["lambda_function.lambda_handler"]`.
*   **DO NOT** include any `zip` commands or other manual packaging steps within the `Dockerfile` when using the container image deployment model for Lambda.

### Rule 2.4: Rebuilding and Pushing Docker Images to ECR (User Task - AI Guides)
*   AI Agent **DOES NOT** execute `docker build`, `docker tag`, or `docker push` commands directly using `run_terminal_cmd` due to credential and local Docker daemon dependencies.
*   **AI ROLE:** Guide the user through these steps.
*   **Instructions to User (MUST be followed by user):**
    1.  Navigate to the Lambda function's directory (e.g., `image_annotation_system_v2/lambda_functions/thumbnail_lambda/`).
    2.  Build the Docker image: `docker build -t <your_ecr_repo_name>:<tag> . --no-cache --progress=plain`
        *   **ALWAYS** use `--no-cache` to prevent stale layers.
        *   Replace `<your_ecr_repo_name>` (e.g., `comp5349a2-thumbnail-lambda`) and `<tag>` (e.g., `latest`).
    3.  Log in to ECR (if not already): `aws ecr get-login-password --region <aws_region> | docker login --username AWS --password-stdin <aws_account_id>.dkr.ecr.<aws_region>.amazonaws.com`
    4.  Tag the local image to point to the ECR repository: `docker tag <your_local_image_name>:<tag> <aws_account_id>.dkr.ecr.<aws_region>.amazonaws.com/<your_ecr_repo_name>:<tag>`
    5.  Push the image to ECR: `docker push <aws_account_id>.dkr.ecr.<aws_region>.amazonaws.com/<your_ecr_repo_name>:<tag>`
*   **CRITICAL (Obtaining Correct Digest - User Task, AI Requests):**
    *   After the `docker push` command, the user **MUST** provide the **INDEX DIGEST** from the push output (looks like `sha256:abcdef123...`).
    *   The user then **MUST** use this **INDEX DIGEST** to query for the **PLATFORM-SPECIFIC DIGEST** (`linux/amd64`) using the AWS CLI:
        `aws ecr batch-get-image --repository-name <your_ecr_repo_name> --image-ids imageDigest=<INDEX_DIGEST_FROM_PUSH> --region <aws_region>`
    *   From the JSON output of `batch-get-image`, extract the `digest` from the `imageManifest.manifests` array where the platform is `architecture: "amd64"` and `os: "linux"`. This is the digest to be used in CloudFormation.
    *   **AI Agent MUST request this platform-specific digest from the user.**
    *   **PROHIBITED:** AI Agent using the index digest from `docker push` output directly for the Lambda `ImageUri`.

### Rule 2.5: Updating CloudFormation for New Lambda Image (`03-lambda-stack.yaml`)
*   Once the user provides the new **platform-specific image digest** (see Rule 2.4):
*   AI Agent **MUST** update the corresponding `ImageUri` parameter's default value (e.g., `AnnotationLambdaImageUri` or `ThumbnailLambdaImageUri`) in `COMP5349/deployment/03-lambda-stack.yaml`.
    *   The format will be: `<aws_account_id>.dkr.ecr.<aws_region>.amazonaws.com/<your_ecr_repo_name>@<PLATFORM_SPECIFIC_DIGEST>`
*   For Lambda functions defined in this template:
    *   `PackageType` **MUST** be `Image`.
    *   `Handler` and `Runtime` properties **MUST NOT** be present.
*   **DO NOT** modify or add Lambda Layer configurations unless explicitly instructed by the user to revert/change deployment strategy.

## 3. CloudFormation Template Modifications (General)

### Rule 3.1: `02-application-stack.yaml` (Application Infrastructure)
*   This template primarily defines S3, RDS, EC2 Auto Scaling Group, and Application Load Balancer.
*   **S3 EventBridge Notification:** The `OriginalImagesBucket` resource (parameter name: `OriginalImagesBucketName`) **MUST** have `EventBridgeConfiguration.EventBridgeEnabled: true` set in its `NotificationConfiguration`. This is critical for triggering the Lambdas via EventBridge.

### Rule 3.2: `03-lambda-stack.yaml` (Lambda and Supporting Resources)
*   For Lambda function resource updates (e.g., `AnnotationLambdaFunction`, `ThumbnailLambdaFunction`), refer to Rule 2.5.
*   **EventBridge Rule (`S3UploadEventRule`):**
    *   This rule **MUST** target the default EventBridge bus.
    *   Its `EventPattern` **MUST** correctly filter for `s3:ObjectCreated:*` events.
    *   The `source` in the `EventPattern` **MUST** be `["aws.s3"]`.
    *   The `detail.bucket.name` in `EventPattern` **MUST** reference the `OriginalImagesBucketName` parameter passed from `02-application-stack.yaml` or a direct parameter.
    *   Targets **MUST** be the ARNs of `AnnotationLambdaFunction` and `ThumbnailLambdaFunction`.
    *   Associated `AWS::Lambda::Permission` resources **MUST** allow `events.amazonaws.com` to invoke these Lambda functions, referencing the `S3UploadEventRule` ARN.

### Rule 3.3: Parameters and Outputs in CloudFormation
*   **WHEN** introducing new configurable values (e.g., a new S3 bucket name, an API endpoint), **PREFER** adding new `Parameters` to the CloudFormation templates with clear descriptions and sensible default values.
*   **WHEN** a resource created in one CloudFormation stack (e.g., S3 bucket name from `02-application-stack.yaml`) is needed by resources in another stack (e.g., for Lambda environment variables or EventBridge rules in `03-lambda-stack.yaml`), **ALWAYS** expose the necessary attributes (like ARN or Name) via `Outputs` in the source stack and reference them using `Fn::ImportValue` or by passing as parameters in the consuming stack.

## 4. Testing (`pytest`)

### Rule 4.1: `pytest.ini` Configuration
*   The `pytest.ini` file at the project root (`COMP5349/pytest.ini`) configures test discovery.
*   The `norecursedirs` setting **MUST** include patterns like `*/package/`, `.*\.egg-info/`, `.pytest_cache/` to prevent `pytest` from attempting to collect tests from Lambda packaging artifacts or cache directories, which can lead to errors.

### Rule 4.2: Writing and Modifying Unit Tests
*   Unit tests for Lambda functions are located in `COMP5349/image_annotation_system_v2/tests/lambda_functions/{lambda_name}/`.
*   **ALWAYS** use mocking (e.g., `unittest.mock` via `pytest-mock`) for external dependencies such as AWS service clients (Boto3), database connections, and external API calls (Gemini).
*   **WHEN** Lambda function logic is modified, corresponding unit tests **MUST** be reviewed and updated to reflect the changes.
*   Lambda test cases **MUST** specifically cover event parsing logic for both EventBridge-wrapped S3 events (`event['detail']`) and direct S3 events (`event['Records']`).

## 5. General Coding and Interaction Standards

### Rule 5.1: Custom Exceptions
*   **ALWAYS** use the custom exceptions defined in `custom_exceptions.py` (e.g., `S3InteractionError`, `DatabaseError`, `InvalidInputError`, `GeminiAPIError`) for specific error handling within the Lambda functions.
*   **GeminiAPIError Specifics:** When handling errors from the Gemini API (used via `google-generativeai` SDK with API Key), ensure that `GeminiAPIError` is raised for issues like API key problems, model errors, or content blocking. **Do not** assume Vertex AI SDK exceptions here.
*   The `custom_exceptions.py` file is located alongside `lambda_function.py` within each Lambda function's specific directory (e.g., `COMP5349/image_annotation_system_v2/lambda_functions/annotation_lambda/custom_exceptions.py`).
*   The `Dockerfile` for each Lambda **MUST** include a `COPY custom_exceptions.py ${LAMBDA_TASK_ROOT}/` directive.

### Rule 5.2: Logging Practices
*   **ALWAYS** adhere to the JSON logging format specified in the `COMP5349 Assignment 2 - 项目设计文档.md`.
*   In Lambda functions, **ALWAYS** include the `aws_request_id` (from the `context` object) in log entries.
*   In the Flask web application (if modifications are requested), **ALWAYS** include the `request_id` (from `flask.g`) in log entries.

### Rule 5.3: Referencing the Main Design Document
*   For detailed specifications on Naming Conventions, overall Error Handling Strategy, Python version, general AWS resource configurations, specific Lambda function business logic, and database schema, **ALWAYS** refer to `COMP5349/COMP5349 Assignment 2 - 项目设计文档.md`.
*   **Gemini API Implementation Detail:** The `annotation_lambda`'s image understanding capability is implemented using the **Google Gemini API via the `google-generativeai` Python SDK and an API Key (`GEMINI_API_KEY` environment variable)**. This is a critical distinction from using the Vertex AI SDK or service account based authentication for this specific functionality. Ensure all code, documentation, and guidance aligns with this approach.
*   This `shrimp-rules.md` document provides AI Agent-specific *operational* instructions, overrides, or clarifications that build upon the main design document.

### Rule 5.4: AI Agent Interaction with User
*   **WHEN** the user requests a build and deployment sequence for Lambda functions, **ALWAYS** assume the full cycle is required:
    1.  Code changes (if any, by AI).
    2.  Guidance to user for Docker image build.
    3.  Guidance to user for Docker image push to ECR.
    4.  Requesting the new platform-specific ECR image digest from the user.
    5.  Updating the CloudFormation template (`03-lambda-stack.yaml`) with the new digest (by AI).
    6.  Informing the user that the CloudFormation template is updated and ready for them to deploy.
*   **DO NOT** assume the user has partially completed these steps unless explicitly stated by the user.
*   **WHEN** providing `docker` or `aws cli` commands to the user, **ALWAYS** clarify that these commands are intended for execution in the user's local terminal environment.
*   **PRIORITIZE** completing the user's request end-to-end. If blocked (e.g., waiting for the user to provide a new ECR image digest), clearly state what information is needed from the user to proceed.

## 6. AI Decision-Making Aids

### Rule 6.1: Handling Ambiguous User Requests
*   **IF** a user request is vague (e.g., "update the lambda," "fix the S3 permissions"), AI Agent **MUST FIRST** attempt to clarify by:
    1.  Reviewing the last few turns of the conversation for immediate context.
    2.  Checking the "Primary Interaction Files" (see Section 1.2) for recent changes or common error points related to the vague terms. (e.g., if "S3 permissions issue", check Lambda IAM roles, S3 bucket policies in CFN templates).
    3.  **ONLY IF** the above steps do not provide sufficient clarity, **THEN** ask the user for more specific information (e.g., "Which Lambda function are you referring to?", "Could you describe the S3 permission error you are encountering and where it occurs?").
*   **Example (Vague Request: "Fix the S3 upload"):**
    *   *AI Initial Actions:* Review `annotation_lambda/lambda_function.py` and `thumbnail_lambda/lambda_function.py` for S3 `put_object` or `upload_fileobj` calls. Check `03-lambda-stack.yaml` for IAM permissions related to S3 `PutObject` for the Lambda roles. Check `02-application-stack.yaml` for S3 bucket policies or configurations that might affect uploads.
    *   *If still unclear, AI asks user:* "To help me fix the S3 upload, could you specify which Lambda function is failing to upload, or what error message you are seeing?"

### Rule 6.2: Tool Usage Preferences
*   **Code Modifications:** `edit_file` is the primary tool.
*   **File/Directory Information:** `read_file` (for specific line ranges or entire small files as per tool limits) and `list_dir` (for directory contents).
*   **Codebase Search (Semantic):** `codebase_search`. Use the user's phrasing for the query where possible.
*   **Codebase Search (Exact/Regex):** `grep_search`.
*   **Simulating Terminal Commands (for AI to understand user's environment or for user to execute):** `run_terminal_cmd`. **ALWAYS** state that commands generated for the user are for their local terminal execution. AI should not use `run_terminal_cmd` for actions requiring persistent credentials it doesn't have (like `docker push`).
*   **Web Searches:** **AVOID** using `web_search` for project-specific implementation details or logic that should be found within the codebase or design documents. Use `web_search` for:
    *   External library documentation (e.g., a specific Boto3 client method).
    *   AWS service features or limits.
    *   General Python, Docker, or CloudFormation syntax/concepts not specific to this project's internal logic.

### Rule 6.3: Confidence and Proposing Changes
*   **IF** a proposed change is complex, impacts critical infrastructure (e.g., modifying an S3 bucket's public access, changing core RDS properties), or has wide-ranging implications, AI Agent **MUST** clearly state the potential impact and explicitly ask for user confirmation *before* generating the `edit_file` call or finalizing the plan, even if the initial request seemed direct.
*   *Example:* "Modifying the `OriginalImagesBucket` DeletionPolicy in `02-application-stack.yaml` from `Retain` to `Delete` would mean the S3 bucket and its contents will be deleted if the CloudFormation stack is deleted. Is this the intended outcome?"

## 7. Prohibited Actions (For AI Agent)

*   **DO NOT** modify files or components within the `COMP5349/image_annotation_system_v2/web_app/` directory unless *explicitly and specifically* instructed to do so by the user. The primary focus for AI intervention is on the Lambda functions, their deployment, and related AWS infrastructure.
*   **DO NOT** introduce new AWS services, programming languages, or fundamental architectural changes (e.g., switching from EventBridge to SQS for Lambda triggers, changing database type) without explicit user instruction and thorough discussion of implications.
*   **DO NOT** use the `edit_file` tool to create or modify this `shrimp-rules.md` file after its initial creation by this process, unless the user explicitly requests an "update to the AI's project rules document itself."
*   **DO NOT** infer, guess, or hardcode ECR image digests. **ALWAYS** follow the workflow in Rule 2.4 to have the user provide the correct platform-specific digest.
*   **DO NOT** hardcode AWS Account IDs or Regions in generated code or CloudFormation templates.
    *   In CloudFormation, use pseudo parameters like `!Ref "AWS::AccountId"` and `!Ref "AWS::Region"`.
    *   For CLI commands provided to the user, use placeholders like `<aws_account_id>` or `<aws_region>` and instruct the user to replace them.
*   **DO NOT** attempt to execute commands via `run_terminal_cmd` that require persistent, elevated, or user-specific credentials not available to the AI (e.g., `docker login`, `docker push`, `aws configure`). Guide the user to perform these actions in their own environment. 