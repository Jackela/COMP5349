# Deployment Scripts and Notes for Image Annotation System v2

This directory contains the AWS CloudFormation templates used to provision and manage the infrastructure for the Image Annotation System v2. The system is deployed as a series of interdependent stacks.

## CloudFormation Stacks

The primary deployment mechanism involves the following CloudFormation templates, which should be deployed in the specified order:

1.  **`00-ecr-repositories.yaml`**:
    *   **Purpose**: Creates the ECR (Elastic Container Registry) repositories for Docker images.
    *   **Key Resources**: `WebAppECRRepository`, `AnnotationLambdaECRRepository`, `ThumbnailLambdaECRRepository`.
    *   **Note**: This stack should be deployed first, as other stacks depend on these repositories existing or their outputs.

2.  **`01-vpc-network.yaml`**: 
    *   **Purpose**: Sets up the foundational networking infrastructure.
    *   **Key Resources**: VPC, Public/Private Subnets, Internet Gateway, NAT Gateways, Route Tables, Core Security Groups.

3.  **`02-application-stack.yaml`**: 
    *   **Purpose**: Provisions core application-level resources.
    *   **Key Resources**: S3 buckets (for original images and thumbnails), RDS MySQL instance, IAM Roles and Policies, EventBridge rules for S3 event handling.
    *   *(Potentially includes AWS Secrets Manager for sensitive data)*.
    *   **Note**: Does not create ECR repositories (done by `00-ecr-repositories.yaml`) or the primary `LabRole`.

4.  **`03-lambda-stack.yaml`**: 
    *   **Purpose**: Deploys the backend AWS Lambda functions.
    *   **Key Resources**: `annotation_lambda` and `thumbnail_lambda` function definitions, configurations (runtime, handler, memory, timeout, environment variables), and references to their ECR image URIs.
    *   **Note**: Requires ECR image URIs (with platform-specific digests for `linux/amd64`) as parameters. These images must be built and pushed to ECR before deploying/updating this stack.

5.  **`04-ec2-alb-asg-stack.yaml`**: 
    *   **Purpose**: Sets up the web application hosting environment on EC2.
    *   **Key Resources**: EC2 Launch Template, Auto Scaling Group (ASG), Application Load Balancer (ALB).

## Deployment Process Overview

1.  Deploy the `00-ecr-repositories.yaml` stack to create the ECR repositories.
2.  Ensure all Lambda Docker images (`annotation_lambda`, `thumbnail_lambda`) and the Web App Docker image are built and pushed to their respective ECR repositories (created in step 1).
3.  Obtain the platform-specific (`linux/amd64`) image digests for each Lambda image and the Web App image.
4.  Deploy the remaining CloudFormation stacks sequentially (`01` -> `02` -> `03` -> `04`), providing necessary parameters (like full ECR image URIs with digests).
5.  Apply the database schema (`database/schema.sql`) to the RDS instance after it's provisioned.

Refer to the main project `README.md` (in `image_annotation_system_v2/README.md`) for more comprehensive deployment details, local setup, and architectural overview.

This directory may also contain other deployment-related scripts or notes as the project evolves. 