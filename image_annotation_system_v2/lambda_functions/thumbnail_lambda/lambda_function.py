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

from custom_exceptions import (
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

def _update_thumbnail_info_in_db(db_conn, filename: str, s3_key_original: str, thumbnail_s3_key: Optional[str], 
                               status: str, aws_request_id: str) -> bool:
    """
    Inserts a new record or updates an existing one with thumbnail info.
    This is an UPSERT operation.
    """
    if status not in ['completed', 'failed']:
        raise InvalidInputError(f"Invalid status '{status}'.", error_code='INVALID_STATUS')

    cursor = None
    try:
        cursor = db_conn.cursor()
        
        sql = """
            INSERT INTO images (filename, s3_key_original, s3_key_thumbnail, thumbnail_status)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                s3_key_thumbnail = VALUES(s3_key_thumbnail),
                thumbnail_status = VALUES(thumbnail_status)
        """
        
        cursor.execute(sql, (filename, s3_key_original, thumbnail_s3_key, status))
        db_conn.commit()
        
        affected_rows = cursor.rowcount
        
        if affected_rows > 0:
            logger.info(f"Successfully upserted thumbnail info for {s3_key_original} with status '{status}'",
                       extra={'request_id': aws_request_id})
            return True
        else:
            logger.warning(f"UPSERT operation for {s3_key_original} did not affect any rows (might mean the data was identical).",
                          extra={'request_id': aws_request_id})
            return False

    except mysql.connector.Error as e:
        error_msg = f"Database UPSERT error for thumbnail info: {str(e)}"
        logger.error(error_msg, extra={'request_id': aws_request_id})
        raise DatabaseError(error_msg, error_code='DB_UPSERT_FAILED', original_exception=e)
    finally:
        if cursor:
            cursor.close()

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

    # Configuration from environment variables
    try:
        source_bucket_name = None
        s3_key_original = None

        if 'detail' in event and isinstance(event.get('detail'), dict) and \
           'bucket' in event['detail'] and isinstance(event['detail'].get('bucket'), dict) and \
           'name' in event['detail']['bucket'] and \
           'object' in event['detail'] and isinstance(event['detail'].get('object'), dict) and \
           'key' in event['detail']['object']:
            # EventBridge wrapped S3 event
            logger.info("Parsing event as EventBridge-wrapped S3 event.", extra={'request_id': aws_request_id})
            s3_event_detail = event['detail']
            source_bucket_name = s3_event_detail['bucket']['name']
            s3_key_original = s3_event_detail['object']['key']
        elif 'Records' in event and isinstance(event.get('Records'), list) and \
             len(event['Records']) > 0 and isinstance(event['Records'][0], dict) and \
             's3' in event['Records'][0] and isinstance(event['Records'][0].get('s3'), dict) and \
             'bucket' in event['Records'][0]['s3'] and isinstance(event['Records'][0]['s3'].get('bucket'), dict) and \
             'name' in event['Records'][0]['s3']['bucket'] and \
             'object' in event['Records'][0]['s3'] and isinstance(event['Records'][0]['s3'].get('object'), dict) and \
             'key' in event['Records'][0]['s3']['object']:
            # Direct S3 event (likely for testing or other direct triggers)
            logger.info("Parsing event as direct S3 event.", extra={'request_id': aws_request_id})
            source_bucket_name = event['Records'][0]['s3']['bucket']['name']
            s3_key_original = event['Records'][0]['s3']['object']['key']
        else:
            error_msg = "Event structure is not recognized as S3 or EventBridge-wrapped S3."
            # Log a snippet of the event for easier debugging, avoiding overly large logs
            event_snippet = {k: v for k, v in event.items() if k != 'detail'} # Log top-level keys
            if 'detail' in event and isinstance(event.get('detail'), dict):
                event_snippet['detail_keys'] = list(event['detail'].keys()) # Log keys within detail
            logger.error(error_msg, extra={'request_id': aws_request_id, 'event_snippet': json.dumps(event_snippet, default=str)[:500]})
            raise InvalidInputError(error_msg, error_code='UNKNOWN_EVENT_STRUCTURE')
        
        thumbnail_target_bucket_name = os.environ.get('THUMBNAIL_BUCKET_NAME')
        if not thumbnail_target_bucket_name:
            logger.warning(f"THUMBNAIL_BUCKET_NAME not set. Defaulting to source bucket: {source_bucket_name}", 
                           extra={'request_id': aws_request_id})
            thumbnail_target_bucket_name = source_bucket_name

        target_width_str = os.environ.get('TARGET_WIDTH', '128')
        target_height_str = os.environ.get('TARGET_HEIGHT', '128')
        target_dims = (128, 128) # Default
        try:
            target_dims = (int(target_width_str), int(target_height_str))
        except ValueError:
            logger.warning(f"Invalid TARGET_WIDTH ('{target_width_str}') or TARGET_HEIGHT ('{target_height_str}'). Using default 128x128.",
                          extra={'request_id': aws_request_id})

    except (KeyError, IndexError) as e: # This specific block might be less likely to be hit with the detailed checks above
        error_msg = f"Invalid S3 event structure during parsing attempt: {str(e)}"
        logger.error(error_msg, extra={'request_id': aws_request_id, 'event_snippet': json.dumps(event, default=str)[:500]})
        raise InvalidInputError(error_msg, error_code='INVALID_S3_EVENT_PARSING')
    except InvalidInputError: # Re-raise if our specific InvalidInputError for UNKNOWN_EVENT_STRUCTURE was raised
        raise
    except Exception as e: # Catch other potential errors during initial config (e.g. env var parsing issues if any)
        error_msg = f"Error during initial configuration or S3 event parsing: {str(e)}"
        logger.error(error_msg, exc_info=True, extra={'request_id': aws_request_id})
        # This type of error isn't specific to an image, so we can't update DB status easily.
        # Raising a ConfigurationError is appropriate.
        raise ConfigurationError(error_msg, error_code='INITIAL_CONFIG_ERROR', original_exception=e)

    # Skip if the object is already a thumbnail (e.g. in 'thumbnails/' prefix)
    # This check should ideally use the THUMBNAIL_KEY_PREFIX if defined as an env var
    thumbnail_key_prefix = os.environ.get('THUMBNAIL_KEY_PREFIX', 'thumbnails/')
    if s3_key_original.startswith(thumbnail_key_prefix):
        logger.info(f"Skipping object '{s3_key_original}' as it appears to be a thumbnail.", 
                   extra={'request_id': aws_request_id})
        return {
            'status': 'skipped',
            's3_key_original': s3_key_original,
            'reason': 'is_thumbnail_object'
        }

    db_conn = None
    status_to_set_in_db = 'failed' # Default to failed, explicitly set to completed on success
    thumbnail_s3_key_for_db = None # Will be set on successful upload
    return_payload = {} # Initialize
    processing_exception = None

    # Define original_filename here, once s3_key_original is confirmed
    original_filename = os.path.basename(s3_key_original)

    try:
        logger.info(f"Processing original image s3://{source_bucket_name}/{s3_key_original}", 
                   extra={'request_id': aws_request_id})

        image_bytes = _download_image_from_s3(source_bucket_name, s3_key_original, aws_request_id)
        thumbnail_bytes_io = _generate_thumbnail(image_bytes, target_dims, aws_request_id)

        basename_without_ext, _ = os.path.splitext(original_filename)
        # Ensure prefix ends with a slash if it's not empty
        if thumbnail_key_prefix and not thumbnail_key_prefix.endswith('/'):
            thumbnail_key_prefix += '/'
            
        # Use the (potentially modified) prefix for the key
        thumbnail_s3_key_generated = f"{thumbnail_key_prefix}{basename_without_ext}.jpg"

        _upload_thumbnail_to_s3(thumbnail_target_bucket_name, thumbnail_s3_key_generated, thumbnail_bytes_io, aws_request_id)
        
        status_to_set_in_db = 'completed'
        thumbnail_s3_key_for_db = thumbnail_s3_key_generated # For DB update
        logger.info(f"Thumbnail successfully generated and uploaded to s3://{thumbnail_target_bucket_name}/{thumbnail_s3_key_for_db}", 
                   extra={'request_id': aws_request_id})
        return_payload = {
            'status': 'success',
            's3_key_original': s3_key_original,
            's3_key_thumbnail': thumbnail_s3_key_for_db
        }

    except COMP5349A2Error as e: # Catch our custom exceptions first
        logger.error(f"Processing error for '{s3_key_original}': {e.message} (Code: {e.error_code})", 
                     extra={'request_id': aws_request_id})
        # status_to_set_in_db remains 'failed'
        # thumbnail_s3_key_for_db remains None
        processing_exception = e 
        return_payload = {
            'status': 'error',
            's3_key_original': s3_key_original,
            'error_type': e.__class__.__name__,
            'error_code': e.error_code,
            'message': e.message
        }
    except Exception as e:
        logger.critical(f"Unexpected critical error during processing of '{s3_key_original}': {str(e)}", 
                        exc_info=True, extra={'request_id': aws_request_id})
        # status_to_set_in_db remains 'failed'
        # thumbnail_s3_key_for_db remains None
        processing_exception = COMP5349A2Error(
            f"Unexpected error during thumbnail generation for {s3_key_original}: {str(e)}",
            error_code='THUMBNAIL_UNEXPECTED_ERROR',
            original_exception=e
        )
        return_payload = {
            'status': 'error',
            's3_key_original': s3_key_original,
            'error_type': processing_exception.__class__.__name__,
            'error_code': processing_exception.error_code,
            'message': processing_exception.message
        }

    # --- Database Update Section ---
    # This section will always attempt to update the DB with the determined status.
    try:
        db_conn = _get_db_connection_lambda(aws_request_id)
        logger.info(f"Attempting to update database for '{s3_key_original}' with status '{status_to_set_in_db}' and thumbnail key '{thumbnail_s3_key_for_db}'", 
                   extra={'request_id': aws_request_id})
        _update_thumbnail_info_in_db(
            db_conn=db_conn,
            filename=original_filename,
            s3_key_original=s3_key_original, 
            thumbnail_s3_key=thumbnail_s3_key_for_db, 
            status=status_to_set_in_db, 
            aws_request_id=aws_request_id
        )
    except COMP5349A2Error as db_e: # Catch custom DB errors or config errors from _get_db_connection
        logger.error(f"Database-related error while updating status for '{s3_key_original}': {db_e.message} (Code: {db_e.error_code})", 
                     extra={'request_id': aws_request_id})
        if not processing_exception: # If this is the first error we've encountered
            processing_exception = db_e
            # Update return_payload if it wasn't set by a processing error
            return_payload = {
                'status': 'error',
                's3_key_original': s3_key_original,
                'error_type': db_e.__class__.__name__,
                'error_code': db_e.error_code,
                'message': f"DB update failed after processing: {db_e.message}"
            }
        else:
            logger.warning(f"Original processing error for '{s3_key_original}' occurred. Subsequent DB error: {db_e.message}", 
                          extra={'request_id': aws_request_id})
    except Exception as final_db_e:
        logger.critical(f"Unexpected critical error during final database update for '{s3_key_original}': {str(final_db_e)}", 
                        exc_info=True, extra={'request_id': aws_request_id})
        if not processing_exception:
            processing_exception = COMP5349A2Error(
                f"Unexpected error during final DB update for {s3_key_original}: {str(final_db_e)}",
                error_code='DB_FINAL_UNEXPECTED_ERROR',
                original_exception=final_db_e
            )
            return_payload = {
                'status': 'error',
                's3_key_original': s3_key_original,
                'error_type': processing_exception.__class__.__name__,
                'error_code': processing_exception.error_code,
                'message': processing_exception.message
            }
    finally:
        if db_conn:
            try:
                db_conn.close()
                logger.info("Database connection closed.", extra={'request_id': aws_request_id})
            except Exception as e:
                logger.error(f"Error closing database connection: {str(e)}", 
                               extra={'request_id': aws_request_id})

    if processing_exception:
        # Re-raise the original (or wrapped) processing exception or the DB exception if it was primary
        logger.info(f"Lambda invocation failed for '{s3_key_original}', re-raising exception: {type(processing_exception).__name__}", 
                   extra={'request_id': aws_request_id})
        raise processing_exception
    
    logger.info(f"Lambda invocation completed for '{s3_key_original}'. Status: {return_payload.get('status')}", 
               extra={'request_id': aws_request_id})
    return return_payload 