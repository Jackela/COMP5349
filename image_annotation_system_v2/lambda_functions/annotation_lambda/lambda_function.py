# Handler code for annotation_lambda 
import os
import io
import json
import logging
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import ClientError
import google.generativeai as genai # <--- 使用 google.generativeai
# from google.generativeai.types import HarmCategory, HarmBlockThreshold # 如果需要处理安全设置
# from google.generativeai import types as genai_types # 根据SDK版本，Part的位置可能不同

import mysql.connector
from mysql.connector import errorcode
import magic

# --- Custom Exceptions --- (No longer web_app.utils)
from custom_exceptions import (
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

# Environment variables for Lambda configuration (consider defaults or raise errors if not set)
DB_HOST_LAMBDA = os.environ.get('DB_HOST_LAMBDA') # This seems unused, can be removed if not needed

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

def _update_caption_in_db(db_conn, filename: str, s3_key_original: str, annotation_text: Optional[str], 
                         status: str, aws_request_id: str) -> bool:
    """
    Inserts a new record or updates an existing one with annotation info.
    This is an UPSERT operation.
    """
    if status not in ['completed', 'failed']:
        raise InvalidInputError(f"Invalid status '{status}'.", error_code='INVALID_STATUS')

    cursor = None
    try:
        cursor = db_conn.cursor()
        
        sql = """
            INSERT INTO images (filename, s3_key_original, annotation, annotation_status)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                annotation = VALUES(annotation),
                annotation_status = VALUES(annotation_status)
        """
        cursor.execute(sql, (filename, s3_key_original, annotation_text, status))
        db_conn.commit()
        
        affected_rows = cursor.rowcount
        
        if affected_rows > 0:
            logger.info(f"Successfully upserted annotation info for {s3_key_original} with status '{status}'",
                       extra={'request_id': aws_request_id})
            return True
        else:
            logger.warning(f"UPSERT operation for {s3_key_original} did not affect any rows (might mean the data was identical).",
                          extra={'request_id': aws_request_id})
            return False
            
    except mysql.connector.Error as e:
        error_msg = f"Database UPSERT error for annotation info: {str(e)}"
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

def _call_gemini_api(image_bytes: bytes, aws_request_id: str = "N/A") -> str:
    """Calls the Gemini API using the google-generativeai SDK."""
    api_key = os.environ.get("GEMINI_API_KEY")
    # Ensure you use a model that supports vision, e.g., 'gemini-1.5-flash-latest' or specific vision model.
    model_name = os.environ.get('GEMINI_MODEL_NAME', 'gemini-1.5-flash-latest') 
    prompt_text = os.environ.get('GEMINI_PROMPT', 'Describe this image in detail.')

    if not image_bytes:
        # Add a log for this specific case for easier debugging
        logger.error("Image data for Gemini API call is empty.", extra={'request_id': aws_request_id})
        raise ValueError("Image data cannot be empty")

    if not api_key:
        logger.error("GEMINI_API_KEY not configured.", extra={'request_id': aws_request_id})
        raise ConfigurationError("GEMINI_API_KEY not configured.", error_code='GEMINI_KEY_MISSING')

    try:
        genai.configure(api_key=api_key)
        # For vision models, you typically create the model instance like this:
        model = genai.GenerativeModel(model_name) 
        
        mime_type = 'image/jpeg' # Default
        try:
            # It's good practice to ensure image_bytes is not empty before calling magic
            if image_bytes:
                mime_type = magic.from_buffer(image_bytes, mime=True)
                logger.info(f"Detected MIME type: {mime_type}", extra={'request_id': aws_request_id})
            else: # Should have been caught by the check above, but as a safeguard
                logger.warning("Image bytes are empty before MIME type detection, defaulting to image/jpeg", extra={'request_id': aws_request_id})

        except Exception as e: # Catch generic exception from magic
            logger.warning(f"Could not detect MIME type using python-magic: {e}. Defaulting to image/jpeg.", 
                           extra={'request_id': aws_request_id})
            # Fallback to image/jpeg if magic fails for any reason
            mime_type = 'image/jpeg'


        logger.info(f"Calling Gemini API ({model_name})", extra={'request_id': aws_request_id})
        
        # Constructing the content for the API call
        # The google-generativeai SDK can often infer the type from bytes for common image formats,
        # but explicitly providing the Part with mime_type is more robust.
        # Based on the documentation for `google-generativeai` (not Vertex AI SDK),
        # you provide content as a list, where image parts can be dicts.
        image_part = {'mime_type': mime_type, 'data': image_bytes}
        
        # Sending the request
        # The prompt should be a separate part of the list for clarity
        response = model.generate_content([image_part, prompt_text])

        # Robustly check for blocked content or empty response
        if not response.parts and response.prompt_feedback and response.prompt_feedback.block_reason:
            block_reason_name = response.prompt_feedback.block_reason.name
            error_msg = f"Gemini API content generation was blocked. Reason: {block_reason_name}"
            logger.error(error_msg, extra={'request_id': aws_request_id})
            # Check if there are safety ratings to provide more details
            if response.prompt_feedback.safety_ratings:
                 for rating in response.prompt_feedback.safety_ratings:
                     logger.error(f"Safety Rating: Category: {rating.category.name}, Probability: {rating.probability.name}", 
                                  extra={'request_id': aws_request_id})
            raise GeminiAPIError(error_msg, error_code='CONTENT_BLOCKED')
        
        if not response.text and not response.parts: # If text is empty and parts are also empty (no structured content)
            # This could happen if the model genuinely has nothing to say or another subtle block
            error_msg = "Gemini API returned an empty response (no text or parts)."
            logger.error(error_msg, extra={'request_id': aws_request_id})
            raise GeminiAPIError(error_msg, error_code='EMPTY_RESPONSE')

        caption = response.text # .text should exist if not blocked and parts are present.
        logger.info(f"Successfully received caption from Gemini API: '{caption[:100]}...'", 
                    extra={'request_id': aws_request_id})
        return caption

    except ConfigurationError: # Re-raise config errors
        raise
    except GeminiAPIError: # Re-raise our specific Gemini errors
        raise
    # Specific exceptions from the genai library can be caught here if needed, e.g.
    # except genai.types.BlockedPromptException as e: # Check exact exception name from SDK docs
    #     error_msg = f"Gemini API request was blocked: {str(e)}"
    #     logger.error(error_msg, exc_info=True, extra={'request_id': aws_request_id})
    #     raise GeminiAPIError(error_msg, error_code='CONTENT_BLOCKED_SDK_EXCEPTION', original_exception=e)
    except Exception as e:
        error_msg = f"Gemini API interaction failed: {str(e)}"
        logger.error(error_msg, exc_info=True, extra={'request_id': aws_request_id})
        # Check if it's an AttributeError that mentions 'Part', which was our previous issue
        if isinstance(e, AttributeError) and "'Part'" in str(e):
             logger.error("This looks like the old AttributeError related to 'Part'. Ensure correct SDK and usage.",
                          extra={'request_id': aws_request_id})
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
        bucket_name = None
        object_key = None

        if 'detail' in event and isinstance(event.get('detail'), dict) and \
           'bucket' in event['detail'] and isinstance(event['detail'].get('bucket'), dict) and \
           'name' in event['detail']['bucket'] and \
           'object' in event['detail'] and isinstance(event['detail'].get('object'), dict) and \
           'key' in event['detail']['object']:
            # EventBridge wrapped S3 event
            logger.info("Parsing event as EventBridge-wrapped S3 event.", extra={'request_id': aws_request_id})
            s3_event_detail = event['detail']
            bucket_name = s3_event_detail['bucket']['name']
            object_key = s3_event_detail['object']['key']
        elif 'Records' in event and isinstance(event.get('Records'), list) and \
             len(event['Records']) > 0 and isinstance(event['Records'][0], dict) and \
             's3' in event['Records'][0] and isinstance(event['Records'][0].get('s3'), dict) and \
             'bucket' in event['Records'][0]['s3'] and isinstance(event['Records'][0]['s3'].get('bucket'), dict) and \
             'name' in event['Records'][0]['s3']['bucket'] and \
             'object' in event['Records'][0]['s3'] and isinstance(event['Records'][0]['s3'].get('object'), dict) and \
             'key' in event['Records'][0]['s3']['object']:
            # Direct S3 event (likely for testing or other direct triggers)
            logger.info("Parsing event as direct S3 event.", extra={'request_id': aws_request_id})
            bucket_name = event['Records'][0]['s3']['bucket']['name']
            object_key = event['Records'][0]['s3']['object']['key']
        else:
            error_msg = "Event structure is not recognized as S3 or EventBridge-wrapped S3."
            event_snippet = {k: v for k, v in event.items() if k != 'detail'} 
            if 'detail' in event and isinstance(event.get('detail'), dict):
                event_snippet['detail_keys'] = list(event['detail'].keys())
            logger.error(error_msg, extra={'request_id': aws_request_id, 'event_snippet': json.dumps(event_snippet, default=str)[:500]})
            raise InvalidInputError(error_msg, error_code='UNKNOWN_EVENT_STRUCTURE')

    except (KeyError, IndexError) as e: 
        error_msg = f"Invalid S3 event structure during parsing attempt: {str(e)}"
        logger.error(error_msg, extra={'request_id': aws_request_id, 'event_snippet': json.dumps(event, default=str)[:500]})
        raise InvalidInputError(error_msg, error_code='INVALID_S3_EVENT_PARSING')
    except InvalidInputError: 
        raise
    except Exception as e: 
        error_msg = f"Unexpected error during event parsing: {str(e)}"
        logger.error(error_msg, exc_info=True, extra={'request_id': aws_request_id})
        raise ConfigurationError(error_msg, error_code='EVENT_PARSING_UNEXPECTED_ERROR', original_exception=e)

    # Skip thumbnail objects
    thumbnail_key_prefix = os.environ.get('THUMBNAIL_KEY_PREFIX', 'thumbnails/')
    if object_key.startswith(thumbnail_key_prefix): # Ensure consistent prefix checking
        logger.info(f"Skipping object '{object_key}' as it appears to be a thumbnail (starts with '{thumbnail_key_prefix}').", 
                   extra={'request_id': aws_request_id})
        return {
            'status': 'skipped',
            's3_key': object_key,
            'reason': 'thumbnail_object'
        }
    
    # Initialize variables for processing
    db_conn = None
    status_to_set = 'failed' # Default to failed
    # error_message_for_db = "Unknown processing error" # Not used, caption_to_store is used
    caption_to_store = "Processing did not complete successfully." # Default caption for DB on failure
    return_payload = {} # Initialize to an empty dict
    exception_caught_during_processing = None
    original_filename = os.path.basename(object_key) # Get filename for DB
    
    # Main processing try-except block
    try:
        logger.info(f"Processing original image s3://{bucket_name}/{object_key}", 
                   extra={'request_id': aws_request_id})
                   
        image_bytes = _download_image_from_s3(bucket_name, object_key, aws_request_id)
        
        caption_text_result = _call_gemini_api(image_bytes, aws_request_id)
        
        # If caption_text_result is not empty, it's a success.
        # _call_gemini_api now raises GeminiAPIError for blocked/empty responses.
        status_to_set = 'completed'
        caption_to_store = caption_text_result 
        return_payload = {
            'status': 'success',
            's3_key': object_key,
            'caption_length': len(caption_text_result) if caption_text_result else 0
        }
            
    except S3InteractionError as e:
        logger.error(f"S3 error for '{object_key}': {e.message} (Code: {e.error_code})", 
                     extra={'request_id': aws_request_id})
        status_to_set = 'failed'
        caption_to_store = f"S3 Download Error: {e.message}" # More specific message for DB
        return_payload = {
            'status': 'error', 's3_key': object_key, 'error_type': e.__class__.__name__,
            'error_code': e.error_code, 'message': e.message
        }
        exception_caught_during_processing = e
        
    except GeminiAPIError as e:
        logger.error(f"Gemini API error for '{object_key}': {e.message} (Code: {e.error_code})", 
                     extra={'request_id': aws_request_id})
        status_to_set = 'failed'
        caption_to_store = f"Gemini API Error: {e.message}" # More specific message for DB
        return_payload = {
            'status': 'error', 's3_key': object_key, 'error_type': e.__class__.__name__,
            'error_code': e.error_code, 'message': e.message
        }
        exception_caught_during_processing = e
        
    except ConfigurationError as e: # Catch config errors (e.g., missing API key)
        logger.error(f"Configuration error for '{object_key}': {e.message} (Code: {e.error_code})", 
                     extra={'request_id': aws_request_id})
        status_to_set = 'failed'
        caption_to_store = f"Configuration Error: {e.message}"
        return_payload = {
            'status': 'error', 's3_key': object_key, 'error_type': e.__class__.__name__,
            'error_code': e.error_code, 'message': e.message
        }
        exception_caught_during_processing = e

    except ValueError as e: # Catch ValueError from empty image_bytes
        logger.error(f"ValueError (likely empty image data) for '{object_key}': {str(e)}",
                     extra={'request_id': aws_request_id})
        status_to_set = 'failed'
        caption_to_store = f"ValueError: {str(e)}"
        return_payload = {
            'status': 'error', 's3_key': object_key, 'error_type': 'ValueError',
            'error_code': 'EMPTY_IMAGE_DATA', 'message': str(e)
        }
        exception_caught_during_processing = COMP5349A2Error(
            f"ValueError during processing: {str(e)}",
            error_code='EMPTY_IMAGE_DATA_ERROR', # More specific internal code
            original_exception=e
        )

    except Exception as e: # Catch-all for other unexpected errors
        logger.critical(f"Unexpected critical error during processing of '{object_key}': {str(e)}", 
                        exc_info=True, extra={'request_id': aws_request_id})
        status_to_set = 'failed'
        caption_to_store = f"Unexpected processing error: {str(e)}"
        # Ensure return_payload is structured for error
        return_payload = {
            'status': 'error', 's3_key': object_key, 'error_type': 'UnexpectedError',
            'error_code': 'PROCESSING_UNEXPECTED_ERROR', 'message': caption_to_store
        }
        exception_caught_during_processing = COMP5349A2Error(
            f"Unexpected error during image processing for {object_key}: {str(e)}",
            error_code='ANNOTATION_UNEXPECTED_ERROR', # Specific error code for this type of failure
            original_exception=e
        )
    
    # --- Database Update Section ---
    # This section will always attempt to update the DB with the determined status.
    try:
        db_conn = _get_db_connection_lambda(aws_request_id)
        logger.info(f"Attempting to update database for '{object_key}' (file: '{original_filename}') with status '{status_to_set}'", 
                   extra={'request_id': aws_request_id})
        _update_caption_in_db(
            db_conn=db_conn,
            filename=original_filename, 
            s3_key_original=object_key, 
            annotation_text=caption_to_store, 
            status=status_to_set, 
            aws_request_id=aws_request_id
        )
    except COMP5349A2Error as db_e: # Catch custom DB errors or config errors from _get_db_connection
        logger.error(f"Database-related error while updating status for '{object_key}': {db_e.message} (Code: {db_e.error_code})", 
                     extra={'request_id': aws_request_id})
        if not exception_caught_during_processing: # If this is the first error we've encountered
            exception_caught_during_processing = db_e
            # Update return_payload if it wasn't set by a processing error
            return_payload = {
                'status': 'error', 's3_key': object_key, 'error_type': db_e.__class__.__name__,
                'error_code': db_e.error_code, 
                'message': f"DB update failed after processing: {db_e.message}"
            }
        else: # A processing error already occurred, this DB error is secondary
            logger.warning(f"Original processing error for '{object_key}' occurred. Subsequent DB error: {db_e.message}. The original error will be raised.", 
                          extra={'request_id': aws_request_id})
            # Ensure the original error's payload is what's considered, but log this DB issue.
            if 'message' in return_payload and not return_payload['message'].endswith(db_e.message):
                 return_payload['message'] += f" | DB Update Issue: {db_e.message}"


    except Exception as final_db_e: # Catch any other unhandled DB-related exceptions
        logger.critical(f"Unexpected critical error during final database update for '{object_key}': {str(final_db_e)}", 
                        exc_info=True, extra={'request_id': aws_request_id})
        if not exception_caught_during_processing:
            exception_caught_during_processing = COMP5349A2Error(
                f"Unexpected error during final DB update for {object_key}: {str(final_db_e)}",
                error_code='DB_FINAL_UNEXPECTED_ERROR',
                original_exception=final_db_e
            )
            return_payload = { # Ensure payload reflects this new primary error
                'status': 'error', 's3_key': object_key, 
                'error_type': exception_caught_during_processing.__class__.__name__,
                'error_code': exception_caught_during_processing.error_code, 
                'message': exception_caught_during_processing.message
            }
        else: # A processing error already occurred
             logger.warning(f"Original processing error for '{object_key}' occurred. Subsequent unhandled DB error: {str(final_db_e)}. The original error will be raised.", 
                          extra={'request_id': aws_request_id})
             if 'message' in return_payload and not return_payload['message'].endswith(str(final_db_e)):
                 return_payload['message'] += f" | Unhandled DB Update Issue: {str(final_db_e)}"
        
    finally:
        if db_conn:
            try:
                db_conn.close()
                logger.info("Database connection closed.", extra={'request_id': aws_request_id})
            except Exception as e: # pylint: disable=broad-except
                logger.error(f"Error closing database connection: {str(e)}", 
                               extra={'request_id': aws_request_id})

    if exception_caught_during_processing:
        logger.info(f"Lambda invocation failed for '{object_key}', re-raising exception: {type(exception_caught_during_processing).__name__}", 
                   extra={'request_id': aws_request_id})
        raise exception_caught_during_processing # Raise the primary exception
    
    # If we reach here, it means processing was successful and DB update was attempted (outcome logged)
    # and no exception_caught_during_processing was (re)assigned a primary error status from the DB block.
    logger.info(f"Lambda invocation completed for '{object_key}'. Status: {return_payload.get('status', 'unknown')}", 
               extra={'request_id': aws_request_id, 'final_payload': return_payload})
    return return_payload 

# --- Helper function to handle exceptions and update DB ---
def _handle_exception_and_update_db(db_conn, filename, s3_key, error_message_for_db, exception_obj, aws_request_id):
    """Helper to update DB when an exception occurs during processing."""
    # ---- TEMPORARY DEBUG LOG ----
    logger.critical(f"[_handle_exception_and_update_db] Received error_message_for_db: '{error_message_for_db}' (Type: {type(error_message_for_db)})")
    # ---- END TEMPORARY DEBUG LOG ----
    if db_conn:
        try:
            log_error_detail = exception_obj.message if hasattr(exception_obj, 'message') else str(exception_obj)
            logger.info(f"Attempting to update database for '{s3_key}' (file: '{filename}') with status 'failed' due to error: {log_error_detail}", 
                        extra={'request_id': aws_request_id})
            
            _update_caption_in_db(db_conn, filename, s3_key, error_message_for_db, 'failed', aws_request_id)
            
        except Exception as db_update_e:
            logger.error(f"CRITICAL: Failed to update DB status for {s3_key} after a processing error. DB Error: {db_update_e}", 
                         extra={'request_id': aws_request_id})
    else:
        logger.warning(f"No DB connection available to update status for {s3_key} after error: {str(exception_obj)}",
                       extra={'request_id': aws_request_id}) 