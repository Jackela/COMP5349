# COMP5349 Assignment 2: Image Annotation System v2

## Table of Contents
- [Introduction](#introduction)
- [Key Features](#key-features)
- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Local Development Setup](#local-development-setup)
- [Running the Web Application](#running-the-web-application)
- [Running Tests](#running-tests)
- [Deployment Overview](#deployment-overview)
- [Future Enhancements](#future-enhancements)

## Introduction

The Image Annotation System v2 is an enhanced cloud-based application that provides automated image annotation and thumbnail generation capabilities. Built for COMP5349 Assignment 2, this system demonstrates the implementation of a scalable, resilient cloud architecture using AWS services and modern development practices.

The system features a web interface for image upload and gallery viewing, backed by serverless AWS Lambda functions that handle image processing tasks asynchronously. It leverages Google's Gemini API for intelligent image captioning and implements efficient thumbnail generation for optimized image delivery.

## Key Features

- **User Interface**
  - Intuitive web interface for image uploads
  - Responsive gallery display of images with captions and thumbnails
  - Real-time status updates for processing tasks

- **Image Processing**
  - Automated image captioning using Google's Gemini API
  - Intelligent thumbnail generation with configurable dimensions
  - Support for multiple image formats (JPEG, PNG, GIF)

- **Cloud Architecture**
  - Scalable web application using EC2 Auto Scaling Group
  - High availability through Application Load Balancer
  - Serverless backend processing with AWS Lambda
  - Secure file storage in S3
  - Reliable metadata storage in RDS MySQL

- **Asynchronous Processing**
  - Event-driven architecture using S3 triggers
  - Parallel processing of images for captions and thumbnails
  - Robust error handling and retry mechanisms

## Architecture Overview

The system is built on a three-tier architecture:

1. **Web Application Tier (AWS EC2 with Flask & Docker)**
   - Flask web application (`web_app/app.py`) handles user interactions, image uploads, and gallery display. It is packaged as a Docker container image.
   - Key Endpoints:
     - `/`: Serves the main image upload page.
     - `/upload`: Handles file uploads, stores original images to a dedicated S3 bucket, and records initial metadata in RDS.
     - `/gallery`: Displays processed images with thumbnails and annotations.
     - `/api/image_status/<image_id>`: Provides status updates for individual image processing tasks.
     - `/health`: Standard health check endpoint, used by the ALB.
   - Deployed on EC2 instances within an Auto Scaling Group. The EC2 instances run the Flask application as a Docker container (specified by `WebAppImageUri` in `04-ec2-alb-asg-stack.yaml`).
   - An Application Load Balancer distributes traffic to the EC2 instances.
   - Gunicorn likely runs inside the Docker container to serve the Flask application.
   - Interacts with AWS S3 for image storage and AWS RDS for metadata using `boto3` and `mysql-connector-python` respectively.
   - Relies on an IAM Instance Profile (derived from the provided `LabRoleArn`) for AWS service access.

2. **Storage Tier**
   - S3 buckets for storing original images and thumbnails
   - RDS MySQL database for metadata management
   - Secure access through IAM roles and security groups

3. **Processing Tier (AWS Lambda & EventBridge)**
   - Serverless AWS Lambda functions for backend image processing. These functions are triggered by S3 object creation events in the `S3_IMAGE_BUCKET`, with events routed through AWS EventBridge to the respective Lambdas.
   - Both Lambda functions (`annotation_lambda`, `thumbnail_lambda`) are packaged as self-contained Docker container images (using `public.ecr.aws/lambda/python:3.9-x86_64` as a base) and deployed via AWS ECR. Each Docker image includes all necessary dependencies and shared code, such as `custom_exceptions.py`, which is copied directly into both Lambda packages during their Docker build process.
   - **`annotation_lambda` (Image Captioning)**:
     - *Core Logic*: Downloads the uploaded image from S3, sends it to the Google Gemini API for captioning, and then updates the image metadata in RDS with the generated caption and status (`completed` or `failed`).
     - *Key Libraries*: `boto3`, `google-generativeai`, `mysql-connector-python`, `python-magic` (all included in its Docker image).
     - *Environment Variables Used*: 
       - `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT` (for RDS connection)
       - `GEMINI_API_KEY` (for authenticating with Google Gemini API)
       - `GEMINI_MODEL_NAME` (optional, e.g., `gemini-1.5-flash-latest`)
       - `GEMINI_PROMPT` (optional, e.g., "Describe this image in detail.")
       - `S3_IMAGE_BUCKET` (implicitly, to know where to get the image from the event)
       - `LOG_LEVEL` (optional, for logging verbosity)
   - **`thumbnail_lambda` (Thumbnail Generation)**:
     - *Core Logic*: Downloads the uploaded image from S3, generates a thumbnail using the Pillow library, uploads the thumbnail to a separate `S3_THUMBNAIL_BUCKET`, and then updates the image metadata in RDS with the thumbnail S3 key and status (`completed` or `failed`).
     - *Key Libraries*: `boto3`, `Pillow`, `mysql-connector-python` (all included in its Docker image).
     - *Environment Variables Used*:
       - `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT` (for RDS connection)
       - `S3_IMAGE_BUCKET` (implicitly, to know where to get the image from the event)
       - `S3_THUMBNAIL_BUCKET` (destination for generated thumbnails)
       - `THUMBNAIL_WIDTH`, `THUMBNAIL_HEIGHT` (optional, for thumbnail dimensions, e.g., 128x128)
       - `LOG_LEVEL` (optional, for logging verbosity)

4. **External Services**
   - Google Gemini API for AI-powered image captioning. Note: This is accessed directly using the `google-generativeai` Python SDK and an API Key, not through Vertex AI for this specific image understanding task.
   - Integration through secure API key management

## Tech Stack

- **Cloud Infrastructure**
  - AWS (EC2, Lambda, S3, RDS, ALB, ASG, VPC)
  - IAM for security and access management

- **Backend**
  - Python 3.9
  - Flask web framework
  - Gunicorn WSGI server
  - AWS Lambda for serverless functions

- **Storage & Database**
  - AWS S3 for image storage
  - AWS RDS (MySQL) for metadata
  - mysql-connector-python for database operations

- **Image Processing**
  - Pillow for image manipulation
  - Google Gemini API for AI captioning (using `google-generativeai` SDK and API Key)
  - python-magic for MIME type detection

- **Development & Testing**
  - Pytest for unit testing
  - Pytest-Mock for mocking
  - Pytest-Cov for coverage reporting

## Project Structure

```
image_annotation_system_v2/
├── .gitignore             # Specifies intentionally untracked files that Git should ignore
├── README.md              # This file
├── conftest.py            # Pytest configuration file, for fixtures shared across tests
├── database/              # Database scripts and schema
│   └── schema.sql         # Database schema for RDS MySQL (defines the `images` table)
├── deployment/            # Infrastructure as Code (AWS CloudFormation templates)
│   ├── README.md          # Notes on deployment scripts
│   ├── 00-ecr-repositories.yaml # Defines ECR repositories for Lambda and Web App Docker images.
│   ├── 01-vpc-network.yaml # Defines VPC, subnets, NAT Gateway, Internet Gateway, route tables, security groups.
│   ├── 02-application-stack.yaml # Defines core application resources (e.g., S3 buckets, RDS instance, IAM roles, ECR repos, EventBridge rules).
│   ├── 03-lambda-stack.yaml  # Defines Lambda functions, their configurations and ECR image URIs.
│   ├── 04-ec2-alb-asg-stack.yaml # Defines EC2 Launch Template, Auto Scaling Group, Application Load Balancer.
├── env.example            # Example environment variables file (NOTE: actual filename is env.example)
├── lambda_functions/      # AWS Lambda functions
│   ├── __init__.py        # Makes lambda_functions a Python package
│   ├── annotation_lambda/ # Image captioning Lambda
│   │   ├── Dockerfile       # Dockerfile for the Lambda function
│   │   ├── lambda_function.py
│   │   ├── requirements.txt # Dependencies for this Lambda
│   │   └── custom_exceptions.py # Local module for custom exceptions, copied into the Docker image
│   └── thumbnail_lambda/  # Thumbnail generation Lambda
│       ├── Dockerfile
│       ├── lambda_function.py
│       ├── requirements.txt
│       └── custom_exceptions.py # Also uses this local module, copied into the Docker image
├── package_lambda.py      # LEGACY SCRIPT: Originally for creating .zip deployment packages. Current deployment uses Docker images.
├── requirements-dev.txt   # Python dependencies for development (e.g., linters, test tools)
├── setup.py               # Python package setup script (if the project is installable)
├── tests/                 # Test suite
│   ├── web_app/           # Web app tests
│   └── lambda_functions/  # Lambda function tests
│       ├── annotation_lambda/
│       └── thumbnail_lambda/
└── web_app/               # Flask web application
    ├── static/            # Static assets (CSS, JavaScript, images)
    ├── templates/         # HTML templates (Jinja2)
    ├── utils/             # Utility modules for the web application
    ├── app.py             # Main Flask application file
    └── requirements.txt   # Python dependencies for the web application
```

## Local Development Setup

### Prerequisites

- Python 3.9 (as used in Lambda base images and for web_app consistency)
- pip (Python package installer)
- Virtual environment tool (e.g., `venv`)
- Docker Desktop (or Docker Engine) for building Lambda container images locally.
- AWS CLI, configured with appropriate credentials and default region.
- MySQL client (optional, for direct database interaction).
- An AWS account with access to relevant services (S3, RDS, Lambda, ECR, EventBridge, CloudFormation).
- A Google Cloud Project with the Gemini API enabled and an API Key.

### Setup Steps

1. **Clone and Setup Environment**
   ```bash
   git clone <repository_url> # Replace <repository_url> with the actual URL
   cd image_annotation_system_v2
   python3 -m venv venv
   source venv/bin/activate  # Linux/macOS
   # or
   # venv\Scripts\activate     # Windows (use this if you are on Windows PowerShell/cmd)
   ```

2. **Install Dependencies**
   ```bash
   # Core application dependencies (Web app and Lambdas)
   pip install -r web_app/requirements.txt
   pip install -r lambda_functions/annotation_lambda/requirements.txt
   pip install -r lambda_functions/thumbnail_lambda/requirements.txt
   
   # Development and testing dependencies
   pip install -r requirements-dev.txt
   ```

3. **Environment Configuration**
   Create a `.env` file by copying `env.example` (note: your project has `env.example` not `.env.example` based on file listing):
   ```bash
   cp env.example .env 
   ```
   Then, edit the `.env` file with your specific configurations. This file is primarily for local Flask development.

   **Key Environment Variables (for local web_app via `.env` and for deployed Lambdas via CloudFormation/AWS Console):**

   *   **Flask Web Application (`web_app/app.py`):**
       *   `FLASK_SECRET_KEY`: Secret key for Flask session management.
       *   `S3_IMAGE_BUCKET`: S3 bucket for original images.
       *   `S3_THUMBNAIL_BUCKET`: S3 bucket for thumbnails.
       *   `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT`: RDS MySQL details.
       *   `LOG_LEVEL`: (Optional) e.g., `INFO`, `DEBUG`.

   *   **`annotation_lambda`:**
       *   `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT`: RDS MySQL details.
       *   `GEMINI_API_KEY`: Google Gemini API Key.
       *   `GEMINI_MODEL_NAME`: (Optional) e.g., `gemini-1.5-flash-latest`.
       *   `GEMINI_PROMPT`: (Optional) e.g., "Describe this image in detail.".
       *   `S3_IMAGE_BUCKET`: (Usually passed in event, but good to be aware if needed directly).
       *   `LOG_LEVEL`: (Optional).

   *   **`thumbnail_lambda`:**
       *   `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT`: RDS MySQL details.
       *   `S3_THUMBNAIL_BUCKET`: Destination S3 bucket for thumbnails.
       *   `S3_IMAGE_BUCKET`: (Usually passed in event).
       *   `THUMBNAIL_WIDTH`, `THUMBNAIL_HEIGHT`: (Optional) e.g., 128.
       *   `LOG_LEVEL`: (Optional).

   *Note: For deployed Lambdas, these are set in their AWS environment, often managed by CloudFormation.* 

4. **Database Setup**
   ```bash
   # Create database
   mysql -u <user> -p
   CREATE DATABASE image_annotation_db;
   
   # Apply schema
   mysql -u <user> -p image_annotation_db < database/schema.sql
   ```

## Running the Web Application

1. **Set Environment Variables**
   Ensure all required environment variables are set in your `.env` file or system environment.

2. **Start the Application**
   ```bash
   cd web_app
   python app.py
   ```
   The application will be available at http://127.0.0.1:5000

## Running Tests

From the project root directory:

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=web_app --cov=lambda_functions # Ensure paths are correct for your project
```

## Deployment Overview

The system is deployed on AWS using a set of AWS CloudFormation templates located in the `deployment/` directory. These templates provision and manage all necessary cloud resources in a specific order. It is crucial to deploy these stacks sequentially as later stacks may depend on resources created by earlier ones.

**Prerequisites for Deployment:**
*   **IAM Role (`LabRole`)**: A pre-existing IAM role (identified by `LabRoleArn` parameter in `03-lambda-stack.yaml` and `04-ec2-alb-asg-stack.yaml`) must exist with necessary permissions for Lambda (S3, RDS, CloudWatch, EventBridge invocation) and EC2 (S3, CloudWatch, ECR pull, potentially RDS).

1.  **Infrastructure Stacks (CloudFormation):**
    *   **`00-ecr-repositories.yaml`**: Creates the ECR repositories.
        *   **Key Resources**: `WebAppECRRepository`, `AnnotationLambdaECRRepository`, `ThumbnailLambdaECRRepository`.
        *   **Must be deployed first.**
    *   **`01-vpc-network.yaml`**: Sets up the foundational networking infrastructure (VPC, subnets, etc.).
    *   **`02-application-stack.yaml`**: Provisions core application-level resources (S3, RDS). 
        *   **Key Resources**: S3 buckets for original images (`S3_IMAGE_BUCKET`) and thumbnails (`S3_THUMBNAIL_BUCKET`), RDS MySQL database instance.
        *   *Note: This stack does not create ECR repositories (done by `00-ecr-repositories.yaml`) or the primary IAM execution roles for Lambda/EC2 (these are assumed to be prerequisites and passed as `LabRoleArn`).*
    *   **`03-lambda-stack.yaml`**: Deploys the Lambda functions and their triggers. 
        *   Relies on ECR repositories created by `00-ecr-repositories.yaml`.
        *   Requires the full ECR image URIs (including tag/digest) as parameters.
    *   **`04-ec2-alb-asg-stack.yaml`**: Sets up the web application hosting environment.
        *   Relies on ECR repository created by `00-ecr-repositories.yaml` for the web app image.
        *   Requires the full web app ECR image URI (including tag/digest) as a parameter.

2.  **Image Building and Pushing (User Responsibility):**
    *   **Web Application Docker Image**: Build the Docker image for the Flask web application (`web_app/Dockerfile` - *assuming one exists or is implied by `WebAppImageUri`*) and push it to its ECR repository.
    *   **Lambda Docker Images**: For each Lambda function (`annotation_lambda`, `thumbnail_lambda`):
        *   Build the Docker image from its respective directory.
        *   Push the image to its ECR repository.
        *   Retrieve the platform-specific (`linux/amd64`) image digest.

3.  **CloudFormation Deployment (User Responsibility):**
    *   Deploy stacks in numerical order: `00-ecr-repositories.yaml` -> `01-vpc-network.yaml` -> `02-application-stack.yaml` -> `03-lambda-stack.yaml` (providing Lambda image URIs with digests) -> `04-ec2-alb-asg-stack.yaml` (providing Web App image URI).
    *   Provide all required parameters for each stack (e.g., `LabRoleArn`, `GeminiApiKey`, database credentials, ECR image URIs).

4.  **Post-Deployment Steps (User Responsibility):**
    *   **Database Schema Application**: After the RDS instance is provisioned by `02-application-stack.yaml`, the schema in `database/schema.sql` must be applied manually or via script.

*(The section previously titled "Lambda Function Deployment (Docker/ECR Workflow - CRITICAL)" has been integrated into the above points for clarity and flow. The critical nature of obtaining the correct image digest remains.)*

Detailed deployment scripts, specific commands, and further instructions for each step should ideally be maintained in the `deployment/` directory or a dedicated operations guide, referencing the `COMP5349/COMP5349 Assignment 2 - 项目设计文档.md` for architectural details.

## Future Enhancements

- Enhanced MIME type detection for better file handling
- Comprehensive integration testing suite
- User authentication and authorization
- Image processing optimization
- Monitoring and alerting system
- Automated deployment pipeline 