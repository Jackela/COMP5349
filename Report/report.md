# COMP5349 Assignment 2: Enhanced Image Annotation System Deployment Report

**Student ID:** 540096246  
**Student Name:** Weixuan Kong  
**AWS Account ID:** 032664865485  
**AWS Region:** us-east-1  
**Course:** COMP5349 Cloud Computing  
**Semester:** 1/2025  

---

## 1. Introduction

This report documents the design, implementation, and deployment of an enhanced image annotation system that integrates traditional web application architecture with modern serverless computing capabilities on Amazon Web Services (AWS). The system represents a significant evolution from Assignment 1, incorporating enterprise-grade scalability, fault tolerance, and automated processing workflows.

The deployed solution demonstrates a hybrid cloud architecture that combines the reliability of traditional web servers with the cost-effectiveness and scalability of serverless functions. At its core, the system enables users to upload images through a web interface, which then triggers an automated pipeline for AI-powered annotation generation and thumbnail creation, all while maintaining high availability through auto-scaling mechanisms.

**Key Architectural Innovations:**

1. **Event-Driven Processing**: The system employs Amazon EventBridge to decouple the web application from backend processing tasks, ensuring that user uploads immediately trigger both annotation and thumbnail generation workflows without blocking the user experience.

2. **Containerized Serverless Functions**: Both Lambda functions are deployed as container images rather than traditional ZIP packages, enabling better dependency management and more consistent runtime environments, particularly important for the Google Gemini API integration and image processing libraries.

3. **Auto-Scaling Web Tier**: The web application layer is designed for enterprise-scale traffic handling with Application Load Balancer distribution across multiple EC2 instances managed by an Auto Scaling Group, ensuring both high availability and cost optimization.

4. **Asynchronous User Experience**: The frontend implements modern AJAX polling mechanisms to provide real-time status updates for image processing, eliminating the need for users to manually refresh pages while maintaining excellent user experience during high-load scenarios.

5. **Unified Data Management**: A carefully designed MySQL schema supports concurrent Lambda function updates through UPSERT operations, preventing race conditions while maintaining data consistency across the distributed processing pipeline.

This architecture addresses real-world requirements for image processing applications, including handling variable traffic loads, managing external API dependencies, and providing resilient error handling mechanisms. The system's design prioritizes both operational excellence and cost optimization, making it suitable for production deployment in enterprise environments.

---

## 2. Architecture Diagram

The enhanced image annotation system employs a hybrid architecture that separates concerns between user-facing web services and backend processing tasks. This section presents two complementary architectural views that demonstrate the system's comprehensive design.

### 2.1 Web Application Architecture

The web application architecture focuses on delivering a scalable, highly available user interface for image uploads and gallery viewing. This tier handles all user interactions and maintains the system's operational state.

![](./images/Web_App%20Architecture%20Diagram.png)
*Figure 2.1: Web Application Architecture Diagram*

**Key Components:**

* **VPC Network**: 10.0.0.0/16 with public/private subnet distribution across two Availability Zones.
* **Application Load Balancer**: Internet-facing ALB with health checks on `/health` endpoint.
* **Auto Scaling Group**: Min: 1, Max: 2, Desired: 1, with a target tracking policy for CPU utilization.
* **EC2 Instances**: t3.micro running a containerized Flask application with Gunicorn WSGI.
* **RDS Database**: db.t3.micro MySQL 8.0.35 with 20GB storage, located in a private subnet.
* **S3 Storage**: Separate S3 buckets for original images and generated thumbnails.

### 2.2 Serverless Architecture

The serverless architecture handles automated image processing tasks triggered by user uploads. This event-driven system ensures scalable, cost-effective processing without impacting user experience.

![](./images/Serverless%20Architecture.png)
*Figure 2.2: Serverless Architecture Diagram*

**Event Flow:**

1. An image upload to the S3 `uploads/` prefix triggers an `ObjectCreated` event.
2. The event is sent to the default Amazon EventBridge event bus.
3. An EventBridge rule matches the event and routes it to two Lambda functions simultaneously.
4. The Annotation Lambda calls the Google Gemini API for an image description, while the Thumbnail Lambda generates a resized image using the Pillow library.
5. Both functions update the shared RDS database with their respective processing results and status.

### 2.3 Integration Between Components

The two architectures are tightly integrated yet loosely coupled, forming a cohesive system:

* **Shared Database**: Both the web application (EC2) and the Lambda functions access the same RDS instance to read and write image metadata, ensuring a single source of truth.
* **S3 Event Trigger**: The primary integration point is the S3 bucket. The web application's action (uploading an image) directly and asynchronously triggers the entire serverless processing pipeline.
* **Status Synchronization**: The web application uses AJAX polling to periodically query the RDS database for status updates (pending, completed), providing a seamless real-time experience to the end-user.
* **Shared Infrastructure**: Both architectures operate within the same VPC, leveraging shared networking (like the NAT Gateway for Lambda's external access) and IAM roles for secure, consistent resource access.

---

## 3. Web Application Deployment

### 3.1 Compute Environment

#### 3.1.1 EC2 Auto Scaling Group Configuration

The web application is deployed on EC2 instances managed by an Auto Scaling Group to ensure high availability and dynamic scaling based on traffic.

**Launch Template Specifications:**

* **Instance Type**: t3.micro
* **AMI**: ami-01f5a0b78d6089704 (Amazon Linux 2)
* **Instance Profile**: LabRole
* **Security Groups**: comp5349a2-EC2-SG

**Auto Scaling Configuration:**

* **Minimum Capacity**: 1 instance
* **Maximum Capacity**: 2 instances
* **Desired Capacity**: 1 instance
* **Health Check Type**: ELB with a 300-second grace period.
* **Scaling Policy**: A Target Tracking policy was configured to maintain an average CPU utilization of 20%, ensuring the system can scale out proactively under moderate load.

![](./images/ImageAnnotation-WebApp-ScaleOutPolicy.png)
*Figure 3.1: ASG Target Tracking Scaling Policy*

#### 3.1.2 Network Settings

**VPC Configuration:**

* **VPC CIDR**: 10.0.0.0/16
* **Public Subnets**: 10.0.1.0/24 (us-east-1a), 10.0.2.0/24 (us-east-1b)
* **Private Subnets**: 10.0.101.0/24 (us-east-1a), 10.0.102.0/24 (us-east-1b)

**Network Components:**

* **Internet Gateway**: `comp5349a2-IGW` for ingress traffic.
* **NAT Gateway**: `comp5349a2-NATGateway` placed in a public subnet to provide outbound internet access for resources in private subnets.
* **Route Tables**: Separate route tables for public subnets (routing to IGW) and private subnets (routing to NAT Gateway).

#### 3.1.3 Security Configurations

**Security Groups:**

* **ALB Security Group** (`comp5349a2-ALB-SG`): Allows inbound HTTP (80) from `0.0.0.0/0` and allows outbound traffic on port 5000 to the EC2 security group.
* **EC2 Security Group** (`comp5349a2-EC2-SG`): Allows inbound traffic on port 5000 from the ALB security group and allows outbound traffic to the RDS security group on port 3306 and to the internet on port 443.

**IAM Configuration:**

* **Role**: `LabRole` is used for EC2 instances and Lambda functions, providing necessary permissions for S3 access, RDS connectivity, and CloudWatch logging.

### 3.2 Load Balancer Setup

An Application Load Balancer is used to distribute incoming traffic across the EC2 instances, enhancing fault tolerance and availability.

![](./images/comp5349a2-WebApp-ALB.png)
*Figure 3.2: ALB Listener Forwarding to Target Group*

**Target Group & Health Check Settings:**

* The ALB forwards requests to the `comp5349a2-WebApp-TG` target group.
* Health checks are configured to poll the `/health` endpoint on each instance over port 5000. An instance is considered healthy after 2 consecutive successful checks and unhealthy after 2 failed checks.

![](./images/comp5349a2-WebApp-TG.png)
*Figure 3.3: Target Group Health Check Configuration*

### 3.3 Database Environment

**RDS MySQL Configuration:**

* **Engine**: MySQL 8.0.35
* **Instance Class**: db.t3.micro
* **Storage**: 20 GiB General Purpose SSD (gp3)
* **Multi-AZ**: Disabled for cost optimization in this non-production environment.
* **VPC Security Group**: comp5349a2-DB-SG
* **Database Name**: ImageAnnotationDB

**Database Schema:**
The `images` table is designed to support concurrent updates from the serverless functions using `ON DUPLICATE KEY UPDATE` logic to prevent race conditions.

```sql
CREATE TABLE images (
    id INT AUTO_INCREMENT PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    s3_key_original VARCHAR(1024) NOT NULL UNIQUE,
    s3_key_thumbnail VARCHAR(1024) UNIQUE,
    annotation TEXT,
    annotation_status VARCHAR(50) DEFAULT 'pending',
    thumbnail_status VARCHAR(50) DEFAULT 'pending',
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### 3.4 Storage Environment

**S3 Bucket Configuration:**

* **Originals Bucket**: `comp5349a2-original-images-032664865485-us-east-1`
* **Thumbnails Bucket**: `comp5349a2-thumbnails-032664865485-us-east-1`
* **Versioning**: Enabled on both buckets to prevent accidental data loss.
* **Event Integration**: The originals bucket is configured to send `s3:ObjectCreated:*` events to Amazon EventBridge.

---

## 4. Serverless Component Deployment

### 4.1 Event-Driven Architecture

The serverless backend is architected around events. An S3 `ObjectCreated` event for the `uploads/` prefix triggers an EventBridge rule, which in turn invokes both the annotation and thumbnail Lambda functions in parallel. This decoupling ensures that the backend processing is resilient and independent of the web frontend.

### 4.2 Annotation Function Implementation

This function is responsible for generating AI-based descriptions for uploaded images.

![](./images/comp5349a2-AnnotationLambda.png)
*Figure 4.1: Annotation Lambda Triggered by EventBridge*

**Deployment & Configuration:**

* The function is deployed as a container image (`032664865485.dkr.ecr.us-east-1.amazonaws.com/comp5349a2-annotation-lambda`) from ECR.
* **Memory**: 512 MB
* **Timeout**: 60 seconds
* **API Integration**: Uses the `gemini-1.5-flash-latest` model via the Google Generative AI API.
* **Environment Variables:**
    * `GEMINI_API_KEY`: **********
    * `GEMINI_MODEL_NAME`: gemini-1.5-flash-latest
    * `DB_HOST`: imageannotation-app-s3rds-rdsinstance-dpj3knwasgoc.cxl69jpt8irx.us-east-1.rds.amazonaws.com
    * `DB_NAME`: ImageAnnotationDB
    * `DB_USER`: dbadmin
    * `DB_PASSWORD`: **********

### 4.3 Thumbnail Generator Implementation

This function creates a standardized 128x128 pixel thumbnail for each uploaded image.

![](./images/comp5349a2-ThumbnailLambda.png)
*Figure 4.2: Thumbnail Lambda Triggered by EventBridge*

**Deployment & Configuration:**

* The function is also deployed as a container image (`032664865485.dkr.ecr.us-east-1.amazonaws.com/comp5349a2-thumbnail-lambda`) from ECR.
* **Memory**: 256 MB
* **Timeout**: 30 seconds
* **Image Processing**: Uses the Pillow library with the high-quality LANCZOS resampling algorithm.
* **Environment Variables:**
    * `THUMBNAIL_BUCKET_NAME`: comp5349a2-thumbnails-032664865485-us-east-1
    * `TARGET_WIDTH`: 128
    * `TARGET_HEIGHT`: 128
    * `DB_HOST`: imageannotation-app-s3rds-rdsinstance-dpj3knwasgoc.cxl69jpt8irx.us-east-1.rds.amazonaws.com

---

## 5. Auto Scaling Test Observation

### 5.1 Load Testing Methodology

A custom Python script (`load_tester.py`) was used to simulate concurrent user traffic against the `/gallery` page, which is the most resource-intensive endpoint of the web application.

**Testing Configuration:**

* **Tool**: `load_tester.py`
* **Command**: `python load_tester.py --url http://comp5349a2-WebApp-ALB-79130794.us-east-1.elb.amazonaws.com/gallery --num-requests 4000 --concurrency 20`
* **Total Requests**: 4000
* **Concurrent Users**: 20
* **Test Duration**: 207.72 seconds

### 5.2 Scale Out Observation

The load test successfully increased the average CPU utilization across the Auto Scaling Group, triggering the `WebApp-ScaleOutPolicy` alarm. As shown in Figure 5.1, the CPU utilization (orange line) spiked above the 20% threshold, causing the instance count (blue line) to increase from 1 to 2.

![](./images/CPUUtilization_GroupInServiceCapacity_Metrics.png)
*Figure 5.1: CPU Utilization Spike Triggering Scale Out*

The ASG activity history (Figure 5.2) provides textual confirmation of this event, showing a new instance being launched in response to the alarm.

![](./images/comp5349a2-WebApp-ASG_Activity.png)
*Figure 5.2: Auto Scaling Group Activity Log Confirming Instance Launch*

The EC2 console view (Figure 5.3) provides the final visual confirmation that two instances were running concurrently after the scale-out event completed.

![](./images/comp5349a2-EC2_Instances.png)
*Figure 5.3: EC2 Console Showing Two Running Instances*

### 5.3 Load Distribution Evidence

After the new instance passed its health checks, it was registered with the Application Load Balancer's target group. Figure 5.4 shows both instances in a healthy state, confirming that the ALB was actively distributing traffic between them.

![](./images/comp5349a2-WebApp-TG_Healthy.png)
*Figure 5.4: ALB Target Group with Two Healthy Instances During Peak Load*

### 5.4 Scale In Observation

Once the load test concluded, the CPU utilization dropped below the 20% threshold. After the configured cooldown period, the ASG initiated a scale-in event to optimize costs by terminating the surplus instance. The CloudWatch metric graph (Figure 5.1) shows the instance count returning to 1. The Target Group status (Figure 5.5) confirms that the system successfully returned to its baseline state with a single healthy instance.

![](./images/comp5349a2-WebApp-TG_Scale_In.png)
*Figure 5.5: Target Group Showing Return to a Single Healthy Instance*

### 5.5 Performance Metrics

**Response Time Analysis:**

* **Peak Load Average Response**: 51.9ms (at 19.26 requests per second)
* **Error Rate**: 0% during peak load after implementing caching for pre-signed URLs.

**System Availability**: 100% availability was maintained throughout the scaling events.

---

## 6. Summary and Lessons Learned

### 6.1 Key Achievements

This project successfully implemented a comprehensive cloud-native image annotation system that seamlessly integrates a traditional web application architecture with a modern serverless computing paradigm. The deployment showcases enterprise-grade scalability, fault tolerance, and cost optimization while maintaining an excellent user experience. The successful verification of the auto-scaling and event-driven processing pipelines demonstrates a deep understanding of core AWS services and architectural best practices.

### 6.2 Challenges and Solutions

#### 6.2.1 Auto Scaling Triggering and Calibration

**Challenge**: Initial tests revealed difficulty in effectively increasing CPU utilization by stressing the web application, as it is typically I/O-bound. The initial test target was the upload page (`/`), which has minimal load, fundamentally preventing scaling from triggering.

**Solution**: The test target was revised to the `/gallery` page, which is more computationally intensive due to database queries and template rendering. To ensure scaling could be reliably triggered, baseline tests were conducted, and the scaling policy threshold was adjusted downwards from the default 70% to a more realistic 20%. This data-driven approach allowed for the successful and controlled verification of the entire auto-scaling process.

#### 6.2.2 Gallery Page Performance Bottleneck

**Challenge**: During high-concurrency testing against the `/gallery` endpoint, an extremely high request failure rate was encountered. Analysis identified the bottleneck: each page load required synchronously generating S3 pre-signed URLs for multiple images in a loop. This cryptographic operation consumed significant CPU resources and blocked request processing.

**Solution**: A simple in-memory TTLCache (Time-To-Live Cache) with a 5-minute TTL was implemented for the S3 pre-signed URLs. This drastically reduced server load on subsequent requests, enabling stress tests to complete with a near-zero failure rate under high concurrency and providing clean performance data.

### 6.3 Future Improvements

**Security Enhancements:**

* Integrate AWS Secrets Manager for managing database credentials and API keys.
* Implement VPC Endpoints for S3 and other AWS services to avoid traversing the public internet.
* Deploy AWS WAF on the Application Load Balancer to protect against common web exploits.

**Performance Optimizations:**

* Utilize Amazon ElastiCache (Redis or Memcached) for distributed caching of database queries and S3 URLs.
* Configure Amazon CloudFront CDN to serve static assets and cached gallery pages.
* Enable RDS Read Replicas to offload read-heavy queries from the primary database instance.

### 6.4 Conclusion

This project successfully demonstrates the power of modern cloud architectures in delivering scalable and resilient solutions. The hybrid approach combining a highly available web tier with an event-driven serverless backend provides a robust blueprint for real-world applications. The challenges overcome during testing highlight the importance of meticulous performance analysis and data-driven configuration in a distributed cloud environment. The final deployed system is a testament to the maturity of AWS services in supporting sophisticated, cost-effective, and operationally excellent architectures.

---

## Appendix: Configuration Summary

| Resource Type             | Name/ID                                                                                      | Configuration                                      | Status    |
| ------------------------- | -------------------------------------------------------------------------------------------- | -------------------------------------------------- | --------- |
| VPC                       | comp5349a2-VPC                                                                               | 10.0.0.0/16                                        | Active    |
| ALB                       | comp5349a2-WebApp-ALB                                                                        | comp5349a2-WebApp-ALB-79130794.us-east-1.elb.amazonaws.com | Active    |
| ASG                       | comp5349a2-WebApp-ASG                                                                        | Min:1, Max:2, Desired:1, CPU:20%                   | Active    |
| RDS                       | ImageAnnotationDB                                                                            | db.t3.micro MySQL 8.0.35                           | Available |
| Lambda                    | comp5349a2-AnnotationLambda                                                                  | Container, 512MB, 60s timeout                      | Active    |
| Lambda                    | comp5349a2-ThumbnailLambda                                                                   | Container, 256MB, 30s timeout                      | Active    |
| S3 (Originals)            | comp5349a2-original-images-032664865485-us-east-1                                            | us-east-1, Versioning Enabled                      | Available |
| S3 (Thumbnails)           | comp5349a2-thumbnails-032664865485-us-east-1                                              | us-east-1, Versioning Enabled                      | Available |

**Report Prepared By:** Weixuan Kong  
**Environment:** comp5349a2  
**CloudFormation Stacks:** 5 (ECR, Network, Storage, Lambda, Web App)