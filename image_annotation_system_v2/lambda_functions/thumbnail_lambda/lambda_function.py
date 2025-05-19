# Handler code for thumbnail_lambda
import os
import io
import json
import logging
from typing import Dict, Any, Optional, Tuple

import boto3
from botocore.exceptions import ClientError
from PIL import Image, UnidentifiedImageError  # Pillow for image processing

# --- Database Connector ---
import mysql.connector
from mysql.connector import errorcode

from web_app.utils.custom_exceptions import (
    COMP5349A2Error,
    S3InteractionError,
    DatabaseError,
    ImageProcessingError,
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

def _update_thumbnail_info_in_db(db_conn, original_s3_key: str, thumbnail_s3_key: Optional[str], 
                               status: str, aws_request_id: str) -> bool:
    """
    Updates the thumbnail information and status for an image in the database.
    
    Args:
        db_conn: Database connection object.
        original_s3_key: The S3 key of the original image.
        thumbnail_s3_key: The S3 key of the generated thumbnail, or None if failed.
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
        
        # Update the thumbnail key and status
        sql = """
            UPDATE images 
            SET thumbnail_s3_key = %s, thumbnail_status = %s 
            WHERE original_s3_key = %s
        """
        cursor.execute(sql, (thumbnail_s3_key, status, original_s3_key))
        db_conn.commit()
        
        affected_rows = cursor.rowcount
        cursor.close()
        
        if affected_rows > 0:
            logger.info(f"Successfully updated thumbnail status to '{status}' for {original_s3_key}",
                       extra={'request_id': aws_request_id})
            return True
        else:
            logger.warning(f"No record found for {original_s3_key}",
                          extra={'request_id': aws_request_id})
            return False
            
    except mysql.connector.Error as e:
        error_msg = f"Database error while updating thumbnail info: {str(e)}"
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

def _generate_thumbnail(image_bytes: bytes, target_dims: Tuple[int, int], aws_request_id: str) -> io.BytesIO:
    """
    Generates a thumbnail from image bytes and returns it as a BytesIO object.
    
    Args:
        image_bytes: The original image data as bytes.
        target_dims: Target dimensions as (width, height) tuple.
        aws_request_id: The AWS request ID for logging correlation.
        
    Returns:
        io.BytesIO: A BytesIO object containing the JPEG thumbnail.
        
    Raises:
        ImageProcessingError: If image processing fails.
    """
    try:
        logger.info(f"Generating thumbnail with target dimensions {target_dims}",
                   extra={'request_id': aws_request_id})
        
        # Open image from bytes
        img = Image.open(io.BytesIO(image_bytes))
        logger.info(f"Original image format: {img.format}, size: {img.size}",
                   extra={'request_id': aws_request_id})
        
        # Handle transparency for JPEG output
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            logger.info(f"Converting image with alpha channel to RGB with white background",
                       extra={'request_id': aws_request_id})
            background = Image.new('RGB', img.size, (255, 255, 255))
            img_to_paste = img.convert('RGBA') if img.mode == 'P' and 'transparency' in img.info else img
            background.paste(img_to_paste, (0, 0), img_to_paste if img_to_paste.mode == 'RGBA' else img_to_paste.convert('RGBA'))
            img = background
        elif img.mode != 'RGB':
            logger.info(f"Converting image from {img.mode} to RGB",
                       extra={'request_id': aws_request_id})
            img = img.convert('RGB')
        
        # Generate thumbnail
        img.thumbnail(target_dims, Image.Resampling.LANCZOS)
        
        # Save to BytesIO
        output_io = io.BytesIO()
        img.save(output_io, format='JPEG', quality=85)
        output_io.seek(0)
        
        logger.info(f"Successfully generated thumbnail. New size: {img.size}, format: JPEG",
                   extra={'request_id': aws_request_id})
        return output_io
        
    except UnidentifiedImageError as e:
        error_msg = f"Cannot identify image file: {str(e)}"
        logger.error(error_msg, extra={'request_id': aws_request_id})
        raise ImageProcessingError(error_msg, error_code='INVALID_IMAGE_FORMAT', original_exception=e)
        
    except Exception as e:
        error_msg = f"Pillow processing error: {str(e)}"
        logger.error(error_msg, extra={'request_id': aws_request_id})
        raise ImageProcessingError(error_msg, error_code='PILLOW_PROCESSING_ERROR', original_exception=e)

def _upload_thumbnail_to_s3(bucket_name: str, thumbnail_s3_key: str, 
                          thumbnail_bytes_io: io.BytesIO, aws_request_id: str):
    """
    Uploads a thumbnail to S3.
    
    Args:
        bucket_name: The S3 bucket name.
        thumbnail_s3_key: The S3 key for the thumbnail.
        thumbnail_bytes_io: The thumbnail data as a BytesIO object.
        aws_request_id: The AWS request ID for logging correlation.
        
    Raises:
        S3InteractionError: If S3 operation fails.
    """
    try:
        logger.info(f"Uploading thumbnail to s3://{bucket_name}/{thumbnail_s3_key}",
                   extra={'request_id': aws_request_id})
        
        s3_client = boto3.client('s3')
        s3_client.upload_fileobj(
            thumbnail_bytes_io,
            bucket_name,
            thumbnail_s3_key,
            ExtraArgs={'ContentType': 'image/jpeg'}
        )
        
        logger.info("Successfully uploaded thumbnail to S3",
                   extra={'request_id': aws_request_id})
        
    except ClientError as e:
        error_msg = f"Failed to upload thumbnail to S3: {str(e)}"
        logger.error(error_msg, extra={'request_id': aws_request_id})
        raise S3InteractionError(error_msg, error_code='S3_UPLOAD_FAILED', original_exception=e)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for thumbnail generation.
    
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
        original_object_key = event['Records'][0]['s3']['object']['key']
    except (KeyError, IndexError) as e:
        error_msg = f"Invalid S3 event structure: {str(e)}"
        logger.error(error_msg, extra={'request_id': aws_request_id})
        raise InvalidInputError(error_msg, error_code='INVALID_S3_EVENT')
    
    # Skip thumbnail objects
    if original_object_key.startswith('thumbnails/'):
        logger.info(f"Skipping thumbnail object: {original_object_key}",
                   extra={'request_id': aws_request_id})
        return {
            'status': 'skipped',
            's3_key': original_object_key,
            'reason': 'thumbnail_object'
        }
    
    # Parse thumbnail size from environment variable
    thumbnail_size = os.environ.get('THUMBNAIL_SIZE', '128x128')
    try:
        width, height = map(int, thumbnail_size.split('x'))
        target_dims = (width, height)
    except (ValueError, AttributeError):
        logger.warning(f"Invalid THUMBNAIL_SIZE format: {thumbnail_size}. Using default 128x128",
                      extra={'request_id': aws_request_id})
        target_dims = (128, 128)
    
    # Initialize variables for processing
    db_conn = None
    status_to_set = 'failed'
    error_message_for_db = "Unknown thumbnail processing error"
    final_thumbnail_s3_key = None
    return_payload = None
    exception_caught_during_processing = None
    
    # Main processing try-except block
    try:
        # Download image from S3
        image_bytes = _download_image_from_s3(bucket_name, original_object_key, aws_request_id)
        
        # Generate thumbnail
        thumbnail_bytes_io = _generate_thumbnail(image_bytes, target_dims, aws_request_id)
        
        # Determine thumbnail S3 key
        original_filename = os.path.basename(original_object_key)
        basename_without_ext = os.path.splitext(original_filename)[0]
        final_thumbnail_s3_key = f"thumbnails/{basename_without_ext}.jpg"
        
        # Upload thumbnail to S3
        _upload_thumbnail_to_s3(bucket_name, final_thumbnail_s3_key, thumbnail_bytes_io, aws_request_id)
        
        # Update status for success
        status_to_set = 'completed'
        return_payload = {
            'status': 'success',
            'original_s3_key': original_object_key,
            'thumbnail_s3_key': final_thumbnail_s3_key
        }
        
    except S3InteractionError as e:
        logger.error(f"S3 error: {e.message}", extra={'request_id': aws_request_id})
        status_to_set = 'failed'
        error_message_for_db = f"S3 Error: {e.message}"
        return_payload = {
            'status': 'error',
            'original_s3_key': original_object_key,
            'error_type': 'S3Error',
            'message': e.message
        }
        exception_caught_during_processing = e
        
    except ImageProcessingError as e:
        logger.error(f"Image processing error: {e.message}", extra={'request_id': aws_request_id})
        status_to_set = 'failed'
        error_message_for_db = f"Image Processing Error: {e.message}"
        return_payload = {
            'status': 'error',
            'original_s3_key': original_object_key,
            'error_type': 'ImageProcessingError',
            'message': e.message
        }
        exception_caught_during_processing = e
        
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e.message}", extra={'request_id': aws_request_id})
        status_to_set = 'failed'
        error_message_for_db = f"Configuration Error: {e.message}"
        return_payload = {
            'status': 'error',
            'original_s3_key': original_object_key,
            'error_type': 'ConfigurationError',
            'message': e.message
        }
        exception_caught_during_processing = e
        
    except Exception as e:
        logger.critical(f"Unexpected error: {str(e)}", exc_info=True,
                       extra={'request_id': aws_request_id})
        status_to_set = 'failed'
        error_message_for_db = f"Unexpected error: {str(e)}"
        return_payload = {
            'status': 'error',
            'original_s3_key': original_object_key,
            'error_type': 'UnexpectedError',
            'message': error_message_for_db
        }
        exception_caught_during_processing = COMP5349A2Error(
            "Unexpected error during thumbnail processing",
            error_code='UNEXPECTED_ERROR',
            original_exception=e
        )
    
    # Database update try-except block
    try:
        db_conn = _get_db_connection_lambda(aws_request_id)
        update_success = _update_thumbnail_info_in_db(
            db_conn, original_object_key, final_thumbnail_s3_key, status_to_set, aws_request_id
        )
        
        if not update_success:
            logger.warning(f"Database update did not affect any rows for {original_object_key}",
                          extra={'request_id': aws_request_id})
            
    except DatabaseError as db_e:
        logger.error(f"Database error during status update: {db_e.message}",
                    extra={'request_id': aws_request_id})
        if exception_caught_during_processing:
            logger.error("Original processing error was not updated in database",
                        extra={'request_id': aws_request_id})
            
    except Exception as db_unhandled_e:
        logger.critical(f"Unhandled error during database operations: {str(db_unhandled_e)}",
                       exc_info=True, extra={'request_id': aws_request_id})
        
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