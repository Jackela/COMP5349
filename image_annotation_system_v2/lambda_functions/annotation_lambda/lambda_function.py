# Handler code for annotation_lambda 
import os
import io
import json
import logging
from typing import Dict, Any, Optional, Tuple

import boto3
from botocore.exceptions import ClientError
import google.generativeai as genai
import mysql.connector
from mysql.connector import errorcode

from web_app.utils.custom_exceptions import (
    COMP5349A2Error,
    S3InteractionError,
    DatabaseError,
    GeminiAPIError,
    InvalidInputError,
    ConfigurationError
)

# --- Logger Setup ---
logger = logging.getLogger()
log_level_str = os.environ.get('LOG_LEVEL', 'INFO').upper()
logger.setLevel(getattr(logging, log_level_str, logging.INFO))

def _get_db_connection_lambda(aws_request_id: str) -> mysql.connector.MySQLConnection:
    """
    Establishes a database connection using environment variables.
    
    Args:
        aws_request_id: The AWS request ID for logging correlation.
        
    Returns:
        mysql.connector.MySQLConnection: A database connection object.
        
    Raises:
        ConfigurationError: If required environment variables are missing.
        DatabaseError: If database connection fails.
    """
    # Get database configuration from environment variables
    db_host = os.environ.get('DB_HOST')
    db_user = os.environ.get('DB_USER')
    db_password = os.environ.get('DB_PASSWORD')
    db_name = os.environ.get('DB_NAME')
    db_port = os.environ.get('DB_PORT', '3306')

    # Validate required configuration
    if not all([db_host, db_user, db_password, db_name]):
        missing_vars = [var for var, val in {
            'DB_HOST': db_host,
            'DB_USER': db_user,
            'DB_PASSWORD': db_password,
            'DB_NAME': db_name
        }.items() if not val]
        error_msg = f"Missing required database configuration: {', '.join(missing_vars)}"
        logger.error(error_msg, extra={'request_id': aws_request_id})
        raise ConfigurationError(error_msg, error_code='DB_CONFIG_MISSING')

    try:
        # Attempt to establish database connection
        logger.info(f"Attempting to connect to database {db_host}/{db_name}",
                   extra={'request_id': aws_request_id})
        
        connection = mysql.connector.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name,
            port=int(db_port)
        )
        
        logger.info("Database connection established successfully",
                   extra={'request_id': aws_request_id})
        return connection
        
    except mysql.connector.Error as e:
        error_msg = f"Failed to connect to database: {str(e)}"
        logger.error(error_msg, extra={'request_id': aws_request_id})
        raise DatabaseError(error_msg, error_code='DB_CONNECTION_FAILED', original_exception=e)

def _update_caption_in_db(db_conn, original_s3_key: str, caption_text: Optional[str], 
                         status: str, aws_request_id: str) -> bool:
    """
    Updates the caption and status for an image in the database.
    
    Args:
        db_conn: Database connection object.
        original_s3_key: The S3 key of the original image.
        caption_text: The generated caption text or error message.
        status: The status to set ('completed' or 'failed').
        aws_request_id: The AWS request ID for logging correlation.
        
    Returns:
        bool: True if the update was successful and affected at least one row.
        
    Raises:
        InvalidInputError: If status is not 'completed' or 'failed'.
        DatabaseError: If database operation fails.
    """
    # Validate status
    if status not in ['completed', 'failed']:
        error_msg = f"Invalid status '{status}'. Must be 'completed' or 'failed'."
        logger.error(error_msg, extra={'request_id': aws_request_id})
        raise InvalidInputError(error_msg, error_code='INVALID_STATUS')

    try:
        cursor = db_conn.cursor()
        
        # Update the caption and status
        sql = """
            UPDATE images 
            SET caption = %s, caption_status = %s 
            WHERE original_s3_key = %s
        """
        cursor.execute(sql, (caption_text, status, original_s3_key))
        db_conn.commit()
        
        affected_rows = cursor.rowcount
        cursor.close()
        
        if affected_rows > 0:
            logger.info(f"Successfully updated caption status to '{status}' for {original_s3_key}",
                       extra={'request_id': aws_request_id})
            return True
        else:
            logger.warning(f"No record found for {original_s3_key}",
                          extra={'request_id': aws_request_id})
            return False
            
    except mysql.connector.Error as e:
        error_msg = f"Database error while updating caption: {str(e)}"
        logger.error(error_msg, extra={'request_id': aws_request_id})
        raise DatabaseError(error_msg, error_code='DB_UPDATE_FAILED', original_exception=e)

def _download_image_from_s3(bucket_name: str, object_key: str, aws_request_id: str) -> bytes:
    """
    Downloads an image from S3.
    
    Args:
        bucket_name: The S3 bucket name.
        object_key: The S3 object key.
        aws_request_id: The AWS request ID for logging correlation.
        
    Returns:
        bytes: The image data.
        
    Raises:
        S3InteractionError: If S3 operation fails.
    """
    try:
        logger.info(f"Downloading image from s3://{bucket_name}/{object_key}",
                   extra={'request_id': aws_request_id})
        
        s3_client = boto3.client('s3')
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        image_data = response['Body'].read()
        
        logger.info(f"Successfully downloaded image ({len(image_data)} bytes)",
                   extra={'request_id': aws_request_id})
        return image_data
        
    except ClientError as e:
        error_msg = f"Failed to download image from S3: {str(e)}"
        logger.error(error_msg, extra={'request_id': aws_request_id})
        raise S3InteractionError(error_msg, error_code='S3_DOWNLOAD_FAILED', original_exception=e)

def _call_gemini_api(image_bytes: bytes, aws_request_id: str) -> Optional[str]:
    """
    Calls the Gemini API to generate a caption for an image.
    
    Args:
        image_bytes: The image data as bytes.
        aws_request_id: The AWS request ID for logging correlation.
        
    Returns:
        Optional[str]: The generated caption, or None if generation failed.
        
    Raises:
        ConfigurationError: If required configuration is missing.
        GeminiAPIError: If API call fails.
    """
    # Get Gemini configuration from environment variables
    api_key = os.environ.get('GEMINI_API_KEY')
    model_name = os.environ.get('GEMINI_MODEL_NAME', 'gemini-pro-vision')
    prompt = os.environ.get('GEMINI_PROMPT', 'Describe this image in detail.')

    if not api_key:
        error_msg = "Missing GEMINI_API_KEY environment variable"
        logger.error(error_msg, extra={'request_id': aws_request_id})
        raise ConfigurationError(error_msg, error_code='GEMINI_API_KEY_MISSING')

    try:
        # Configure Gemini
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        
        # TODO: Implement proper MIME type detection using python-magic
        # For now, default to JPEG
        mime_type = 'image/jpeg'
        
        # Prepare image part
        image_part = {
            "mime_type": mime_type,
            "data": image_bytes
        }
        
        logger.info("Calling Gemini API for image captioning",
                   extra={'request_id': aws_request_id})
        
        # Generate content
        response = model.generate_content([prompt, image_part])
        
        # Check for blocked content
        if response.prompt_feedback.block_reason:
            logger.warning(f"Content blocked by Gemini: {response.prompt_feedback.block_reason}",
                          extra={'request_id': aws_request_id})
            return None
            
        # Check for empty response
        if not response.parts or not response.text:
            logger.warning("Empty response from Gemini API",
                          extra={'request_id': aws_request_id})
            return None
            
        caption = response.text.strip()
        logger.info(f"Successfully generated caption ({len(caption)} characters)",
                   extra={'request_id': aws_request_id})
        return caption
        
    except Exception as e:
        error_msg = f"Gemini API error: {str(e)}"
        logger.error(error_msg, extra={'request_id': aws_request_id})
        raise GeminiAPIError(error_msg, error_code='GEMINI_API_ERROR', original_exception=e)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for image annotation.
    
    Args:
        event: The S3 event that triggered the Lambda.
        context: The Lambda context object.
        
    Returns:
        Dict[str, Any]: A response indicating the processing status.
        
    Raises:
        Various exceptions that will trigger Lambda retries and eventually DLQ.
    """
    aws_request_id = context.aws_request_id
    logger.info("Lambda invocation started", extra={'request_id': aws_request_id})
    
    # Extract S3 event details
    try:
        bucket_name = event['Records'][0]['s3']['bucket']['name']
        object_key = event['Records'][0]['s3']['object']['key']
    except (KeyError, IndexError) as e:
        error_msg = f"Invalid S3 event structure: {str(e)}"
        logger.error(error_msg, extra={'request_id': aws_request_id})
        raise InvalidInputError(error_msg, error_code='INVALID_S3_EVENT')
    
    # Skip thumbnail objects
    if object_key.startswith('thumbnails/'):
        logger.info(f"Skipping thumbnail object: {object_key}",
                   extra={'request_id': aws_request_id})
        return {
            'status': 'skipped',
            's3_key': object_key,
            'reason': 'thumbnail_object'
        }
    
    # Initialize variables for processing
    db_conn = None
    status_to_set = 'failed'
    error_message_for_db = "Unknown processing error"
    caption_to_store = None
    return_payload = None
    exception_caught_during_processing = None
    
    # Main processing try-except block
    try:
        # Download image from S3
        image_bytes = _download_image_from_s3(bucket_name, object_key, aws_request_id)
        
        # Generate caption using Gemini
        caption_text_result = _call_gemini_api(image_bytes, aws_request_id)
        
        if caption_text_result:
            status_to_set = 'completed'
            caption_to_store = caption_text_result
            return_payload = {
                'status': 'success',
                's3_key': object_key,
                'caption_length': len(caption_text_result)
            }
        else:
            status_to_set = 'failed'
            caption_to_store = "Caption generation failed or content was blocked."
            return_payload = {
                'status': 'error',
                's3_key': object_key,
                'error_type': 'NoCaptionGenerated',
                'message': caption_to_store
            }
            
    except S3InteractionError as e:
        logger.error(f"S3 error: {e.message}", extra={'request_id': aws_request_id})
        status_to_set = 'failed'
        caption_to_store = f"S3 Download Error: {e.message}"
        return_payload = {
            'status': 'error',
            's3_key': object_key,
            'error_type': 'S3Error',
            'message': e.message
        }
        exception_caught_during_processing = e
        
    except GeminiAPIError as e:
        logger.error(f"Gemini API error: {e.message}", extra={'request_id': aws_request_id})
        status_to_set = 'failed'
        caption_to_store = f"Gemini API Error: {e.message}"
        return_payload = {
            'status': 'error',
            's3_key': object_key,
            'error_type': 'GeminiAPIError',
            'message': e.message
        }
        exception_caught_during_processing = e
        
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e.message}", extra={'request_id': aws_request_id})
        status_to_set = 'failed'
        caption_to_store = f"Configuration Error: {e.message}"
        return_payload = {
            'status': 'error',
            's3_key': object_key,
            'error_type': 'ConfigurationError',
            'message': e.message
        }
        exception_caught_during_processing = e
        
    except Exception as e:
        logger.critical(f"Unexpected error: {str(e)}", exc_info=True,
                       extra={'request_id': aws_request_id})
        status_to_set = 'failed'
        caption_to_store = f"Unexpected processing error: {str(e)}"
        return_payload = {
            'status': 'error',
            's3_key': object_key,
            'error_type': 'UnexpectedError',
            'message': caption_to_store
        }
        exception_caught_during_processing = COMP5349A2Error(
            "Unexpected error during image processing",
            error_code='UNEXPECTED_ERROR',
            original_exception=e
        )
    
    # Database update try-except block
    try:
        db_conn = _get_db_connection_lambda(aws_request_id)
        update_success = _update_caption_in_db(
            db_conn, object_key, caption_to_store, status_to_set, aws_request_id
        )
        
        if not update_success:
            logger.warning(f"Database update did not affect any rows for {object_key}",
                          extra={'request_id': aws_request_id})
            
    except DatabaseError as db_e:
        logger.error(f"Database error during status update: {db_e.message}",
                    extra={'request_id': aws_request_id})
        # If a processing error already occurred, log that we couldn't update its status.
        # Otherwise, this db_e is the primary error to be raised.
        if not exception_caught_during_processing:
            exception_caught_during_processing = db_e
        else:
            logger.error("Original processing error's status could not be updated in the database due to a subsequent DatabaseError.", extra={'request_id': aws_request_id})
            
    except Exception as db_unhandled_e: # Catch any other unhandled DB-related exceptions
        logger.critical(f"Unhandled error during database operations: {str(db_unhandled_e)}",
                       exc_info=True, extra={'request_id': aws_request_id})
        if not exception_caught_during_processing:
            exception_caught_during_processing = COMP5349A2Error(
                f"Unhandled error during database operations: {str(db_unhandled_e)}",
                error_code='DB_UNHANDLED_ERROR',
                original_exception=db_unhandled_e
            )
        else:
            logger.error("Original processing error's status could not be updated in the database due to an unhandled exception during DB ops.", extra={'request_id': aws_request_id})
        
    finally:
        if db_conn:
            try:
                db_conn.close()
                logger.info("Database connection closed",
                           extra={'request_id': aws_request_id})
            except Exception as e:
                logger.error(f"Error closing database connection: {str(e)}",
                           extra={'request_id': aws_request_id})
    
    # Return or re-raise
    if exception_caught_during_processing:
        raise exception_caught_during_processing
        
    logger.info("Lambda invocation completed successfully",
                extra={'request_id': aws_request_id})
    return return_payload 