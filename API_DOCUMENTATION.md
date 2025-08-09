# API Documentation

This document provides details about the RESTful API endpoints available in the Image Annotation System v2.

## Base URL

The base URL for the API will be the DNS name of the Application Load Balancer.
`http://<your_alb_dns_url>`

---

## Get Image Status

Provides the current processing status of a single image, including its annotation and thumbnail generation status. This endpoint is designed to be polled by a client to provide real-time updates to the user.

-   **URL**: `/api/image_status/<image_id>`
-   **Method**: `GET`
-   **URL Parameters**:
    -   `image_id` (integer, required): The unique identifier of the image.

### Success Response (200 OK)

Returned when the image is found in the database.

-   **Content-Type**: `application/json`
-   **Body**:
    ```json
    {
      "id": 123,
      "filename": "my_vacation_photo.jpg",
      "annotation_status": "completed",
      "thumbnail_status": "completed",
      "annotation": "A beautiful sunset over a tropical beach with palm trees.",
      "thumbnail_url": "https://s3-bucket-name.s3.region.amazonaws.com/thumbnails/thumbnail-key.jpg?AWSAccessKeyId=..."
    }
    ```

-   **Field Descriptions**:
    -   `id` (integer): The unique ID of the image.
    -   `filename` (string): The original filename of the uploaded image.
    -   `annotation_status` (string): The status of the captioning task. Can be `pending`, `completed`, or `failed`.
    -   `thumbnail_status` (string): The status of the thumbnail generation task. Can be `pending`, `completed`, or `failed`.
    -   `annotation` (string | null): The AI-generated caption. Will be `null` if the status is not `completed`.
    -   `thumbnail_url` (string | null): A presigned URL to the generated thumbnail. Will be `null` if the thumbnail status is not `completed` or if the URL generation fails.

### Error Responses

-   **404 Not Found**: Returned if no image with the specified `image_id` exists.
    ```json
    {
      "error": "Image not found"
    }
    ```

-   **500 Internal Server Error**: Returned if a database error or other unexpected server-side error occurs.
    ```json
    {
      "error": "Database error"
    }
    ```
