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

1. **Web Application Tier**
   - Flask application deployed on EC2 instances
   - Managed by Auto Scaling Group for scalability
   - Load balanced using Application Load Balancer
   - Handles user interactions and image uploads

2. **Storage Tier**
   - S3 buckets for storing original images and thumbnails
   - RDS MySQL database for metadata management
   - Secure access through IAM roles and security groups

3. **Processing Tier**
   - Serverless Lambda functions for image processing
   - Annotation Lambda for generating image captions
   - Thumbnail Lambda for creating optimized image versions
   - Triggered by S3 object creation events

4. **External Services**
   - Google Gemini API for AI-powered image captioning
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
  - Google Gemini API for AI captioning
  - python-magic for MIME type detection

- **Development & Testing**
  - Pytest for unit testing
  - Pytest-Mock for mocking
  - Pytest-Cov for coverage reporting

## Project Structure

```
image_annotation_system_v2/
├── web_app/               # Flask web application
│   ├── static/           # Static assets
│   ├── templates/        # HTML templates
│   ├── utils/           # Utility modules
│   └── app.py           # Main application file
├── lambda_functions/     # AWS Lambda functions
│   ├── annotation_lambda/  # Image captioning Lambda
│   └── thumbnail_lambda/   # Thumbnail generation Lambda
├── database/            # Database scripts
│   └── schema.sql       # Database schema
├── deployment/          # Infrastructure as Code
├── tests/              # Test suite
│   ├── web_app/        # Web app tests
│   └── lambda_functions/ # Lambda function tests
├── .env.example        # Example environment variables
└── README.md           # This file
```

## Local Development Setup

### Prerequisites

- Python 3.9
- pip (Python package installer)
- Virtual environment tool (venv recommended)
- AWS account (for S3, RDS, Lambda)
- Google Gemini API Key
- MySQL client (optional, for local DB setup)

### Setup Steps

1. **Clone and Setup Environment**
   ```bash
   git clone <repository_url>
   cd image_annotation_system_v2
   python3 -m venv venv
   source venv/bin/activate  # Linux/macOS
   # or
   venv\Scripts\activate     # Windows
   ```

2. **Install Dependencies**
   ```bash
   # Web application
   pip install -r web_app/requirements.txt
   
   # Lambda functions
   pip install -r lambda_functions/annotation_lambda/requirements.txt
   pip install -r lambda_functions/thumbnail_lambda/requirements.txt
   
   # Development dependencies
   pip install pytest pytest-mock pytest-cov
   ```

3. **Environment Configuration**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

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
pytest --cov=web_app --cov=lambda_functions
```

## Deployment Overview

The system is designed for deployment on AWS infrastructure:

1. **Infrastructure Setup**
   - VPC configuration with public and private subnets
   - Security groups and IAM roles
   - RDS MySQL instance
   - S3 buckets for image storage
   - Application Load Balancer and Auto Scaling Group

2. **Application Deployment**
   - Web application deployment to EC2 instances
   - Lambda function deployment
   - S3 event notification configuration
   - Database migration and initialization

Detailed deployment instructions will be provided in the `deployment/` directory.

## Future Enhancements

- Enhanced MIME type detection for better file handling
- Comprehensive integration testing suite
- User authentication and authorization
- Image processing optimization
- Monitoring and alerting system
- Automated deployment pipeline 