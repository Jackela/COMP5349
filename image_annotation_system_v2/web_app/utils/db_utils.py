# db_utils.py - Database interaction utilities 
import os
import mysql.connector
from mysql.connector import errorcode # For specific error codes like ER_DUP_ENTRY
from typing import Optional, List, Dict, Any, Tuple
import datetime # Add if needed later
# Smart import handling
try:
    from .custom_exceptions import COMP5349A2Error, DatabaseError, ConfigurationError, InvalidInputError
except ImportError:
    from utils.custom_exceptions import COMP5349A2Error, DatabaseError, ConfigurationError, InvalidInputError

def get_db_connection() -> mysql.connector.MySQLConnection:
    """
    Establishes and returns a new connection to the MySQL database.
    Reads connection parameters (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT)
    from environment variables.

    Raises:
        ConfigurationError: If essential database environment variables (DB_HOST, 
                            DB_USER, DB_PASSWORD, DB_NAME) are not set.
        DatabaseError: If the database connection fails for other reasons 
                       (e.g., incorrect credentials, database server down).

    Returns:
        mysql.connector.MySQLConnection: An active MySQL database connection object.
    """
    db_host = os.environ.get('DB_HOST')
    db_user = os.environ.get('DB_USER')
    db_password = os.environ.get('DB_PASSWORD')
    db_name = os.environ.get('DB_NAME')
    db_port = os.environ.get('DB_PORT', '3306') # Default to 3306 if not set

    # Pre-condition Check (Environment Variables)
    if not all([db_host, db_user, db_password, db_name]):
        # Logging of this specific error will be done by the caller or a higher-level handler
        # as this utility function should not depend on a specific app logger.
        error_msg = "Database configuration environment variable(s) missing. DB_HOST, DB_USER, DB_PASSWORD, DB_NAME are required."
        raise ConfigurationError(error_msg)

    try:
        # Attempt Connection
        conn = mysql.connector.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name,
            port=db_port,
            connect_timeout=10 # Sensible connect timeout in seconds
        )
        # Logging of successful connection will be handled by the calling context.
        return conn
    except mysql.connector.Error as e:
        # Logging of this specific error will be done by the caller.
        error_msg = f"Failed to connect to database {db_host}/{db_name}."
        raise DatabaseError(message=error_msg, original_exception=e)

def save_initial_image_meta(
    db_conn: mysql.connector.MySQLConnection,
    s3_key_original: str,
    filename: str,
    request_id: Optional[str] = None # For logging context
) -> int:
    """
    Saves initial metadata for a newly uploaded image to the images table.
    Sets annotation to NULL and statuses to 'pending'.

    Args:
        db_conn: An active database connection object.
        s3_key_original: The unique S3 key for the original uploaded image.
                         This key must be unique in the 'images' table.
        filename: The original filename of the uploaded image.
        request_id: Optional. The request ID for logging correlation.
                    (Note: Direct logging from this util is deferred to the caller)

    Raises:
        DatabaseError: If a database error occurs during the insert.
                       Specifically, if s3_key_original violates a UNIQUE constraint,
                       the error_code will be "DB_UNIQUE_VIOLATION".

    Returns:
        int: The auto-incremented ID of the newly inserted record.
    """
    cursor = None  # Initialize cursor to None for the finally block
    try:
        cursor = db_conn.cursor()
        
        # MySQL-compatible INSERT statement matching the new schema
        # annotation, annotation_status, thumbnail_status have defaults
        # uploaded_at, updated_at will be set automatically
        sql_insert_image = """
        INSERT INTO images (filename, s3_key_original) 
        VALUES (%s, %s)
        """
        cursor.execute(sql_insert_image, (filename, s3_key_original))
        db_conn.commit()
        new_id = cursor.lastrowid

        if new_id is None:
            # This case should ideally not happen if auto-increment is working and commit was successful.
            raise DatabaseError(
                message=f"Failed to retrieve new ID after inserting metadata for {s3_key_original}. lastrowid was None.",
                error_code="DB_UPDATE_FAILED"
            )

        return new_id
        
    except mysql.connector.Error as e:
        # The calling code should handle logging of these re-raised exceptions.
        if e.errno == errorcode.ER_DUP_ENTRY:
            # Specific error for unique constraint violation
            raise DatabaseError(
                message=f"Duplicate entry for s3_key_original: {s3_key_original}. This image key already exists in the database.",
                error_code="DB_UNIQUE_VIOLATION",
                original_exception=e
            )
        else:
            # General database error for other issues
            raise DatabaseError(
                message=f"Failed to save initial image metadata for {s3_key_original}. Database error: {e.msg}",
                error_code="DB_UPDATE_FAILED",
                original_exception=e
            )
    finally:
        if cursor:
            cursor.close()

def get_all_image_data_for_gallery(
    db_conn: mysql.connector.MySQLConnection,
    request_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves all image metadata required for the gallery page from the images table,
    ordered by upload time in descending order.

    Args:
        db_conn: An active database connection object.
        request_id: Optional. The request ID for logging correlation.

    Raises:
        DatabaseError: If the database query fails.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, where each dictionary
                              represents an image record. The 'uploaded_at'
                              field will be a datetime.datetime object.
                              Returns an empty list if no images are found.
    """
    cursor = None  # Initialize cursor to None for finally block
    try:
        # Using dictionary=True to get results as dictionaries
        cursor = db_conn.cursor(dictionary=True)
        sql_select_all = """
        SELECT id, filename, s3_key_original, s3_key_thumbnail, 
               annotation, annotation_status, thumbnail_status, 
               uploaded_at, updated_at 
        FROM images 
        ORDER BY uploaded_at DESC
        """
        cursor.execute(sql_select_all)
        results = cursor.fetchall()
        
        return results if results else []
        
    except mysql.connector.Error as e:
        raise DatabaseError(
            message=f"Failed to retrieve image data for gallery. Database error: {e.msg}",
            error_code="DB_SELECT_FAILED",
            original_exception=e
        )
    finally:
        if cursor:
            cursor.close()

def get_image_by_id(
    db_conn: mysql.connector.MySQLConnection,
    image_id: int,
    request_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieves detailed information for a single image by its ID.
    This function is used by the AJAX API endpoint to provide real-time status updates.

    Args:
        db_conn: An active database connection object.
        image_id: The unique ID of the image to retrieve.
        request_id: Optional. The request ID for logging correlation.

    Raises:
        DatabaseError: If the database query fails.
        InvalidInputError: If image_id is not a positive integer.

    Returns:
        Optional[Dict[str, Any]]: A dictionary containing the image record if found,
                                  None if no image with the given ID exists.
    """
    if not isinstance(image_id, int) or image_id <= 0:
        raise InvalidInputError(f"Invalid image_id: {image_id}. Must be a positive integer.")
    
    cursor = None
    try:
        cursor = db_conn.cursor(dictionary=True)
        sql_select_by_id = """
        SELECT id, filename, s3_key_original, s3_key_thumbnail, 
               annotation, annotation_status, thumbnail_status, 
               uploaded_at, updated_at 
        FROM images 
        WHERE id = %s
        """
        cursor.execute(sql_select_by_id, (image_id,))
        result = cursor.fetchone()
        
        return result
        
    except mysql.connector.Error as e:
        raise DatabaseError(
            message=f"Failed to retrieve image data for ID {image_id}. Database error: {e.msg}",
            error_code="DB_SELECT_FAILED",
            original_exception=e
        )
    finally:
        if cursor:
            cursor.close()

def update_caption_in_db(
    db_conn: mysql.connector.MySQLConnection,
    s3_key_original: str,
    annotation_text: Optional[str],
    status: str,
    request_id: Optional[str] = None
) -> bool:
    """
    Updates the annotation text and status for a given image identified by s3_key_original.

    Args:
        db_conn: An active database connection object.
        s3_key_original: The S3 key of the image record to update.
        annotation_text: The annotation text to set. Can be None if status is 'failed'
                      and no specific error message is to be stored in the annotation field.
        status: The new annotation status. Must be 'completed' or 'failed'.
        request_id: Optional. The request ID for logging correlation.

    Raises:
        InvalidInputError: If the provided status is not 'completed' or 'failed'.
        DatabaseError: If a database error occurs during the update.

    Returns:
        bool: True if a record was found and updated (i.e., rowcount > 0),
              False if no record was found with the given s3_key_original.
    """
    if status not in ('completed', 'failed'):
        # Logging by caller
        raise InvalidInputError(
            f"Invalid status parameter '{status}' for update_caption_in_db. Must be 'completed' or 'failed'."
        )

    cursor = None
    try:
        cursor = db_conn.cursor()
        sql_update_annotation = """
        UPDATE images 
        SET annotation = %s, annotation_status = %s 
        WHERE s3_key_original = %s
        """
        cursor.execute(sql_update_annotation, (annotation_text, status, s3_key_original))
        db_conn.commit()
        affected_rows = cursor.rowcount
        return affected_rows > 0
    except mysql.connector.Error as e:
        raise DatabaseError(
            message=f"Failed to update annotation for {s3_key_original}. DB Error: {e.msg}",
            original_exception=e
        )
    finally:
        if cursor:
            cursor.close()

def update_thumbnail_info_in_db(
    db_conn: mysql.connector.MySQLConnection,
    s3_key_original: str,
    s3_key_thumbnail: Optional[str],
    status: str,
    request_id: Optional[str] = None
) -> bool:
    """
    Updates the thumbnail S3 key and processing status for a given image
    identified by s3_key_original.

    Args:
        db_conn: An active database connection object.
        s3_key_original: The S3 key of the original image record to update.
        s3_key_thumbnail: The S3 key of the generated thumbnail. Should be None
                          if the status is 'failed'.
        status: The new thumbnail processing status. Must be 'completed' or 'failed'.
        request_id: Optional. The request ID for logging correlation.

    Raises:
        InvalidInputError: If the provided status is not 'completed' or 'failed'.
        DatabaseError: If a database error occurs during the update.

    Returns:
        bool: True if a record was found and updated (i.e., rowcount > 0),
              False if no record was found with the given s3_key_original.
    """
    if status not in ('completed', 'failed'):
        raise InvalidInputError(
            f"Invalid status parameter '{status}' for update_thumbnail_info_in_db. Must be 'completed' or 'failed'."
        )

    # If status is 'failed', ensure s3_key_thumbnail is None for consistency.
    if status == 'failed' and s3_key_thumbnail is not None:
        s3_key_thumbnail = None

    cursor = None
    try:
        cursor = db_conn.cursor()
        sql_update_thumbnail = """
        UPDATE images 
        SET s3_key_thumbnail = %s, thumbnail_status = %s 
        WHERE s3_key_original = %s
        """
        cursor.execute(sql_update_thumbnail, (s3_key_thumbnail, status, s3_key_original))
        db_conn.commit()
        affected_rows = cursor.rowcount
        return affected_rows > 0
    except mysql.connector.Error as e:
        raise DatabaseError(
            message=f"Failed to update thumbnail info for {s3_key_original}. DB Error: {e.msg}",
            original_exception=e
        )
    finally:
        if cursor:
            cursor.close()

# Other database utility functions will be added here later.
# For example:
# def execute_query(query: str, params: Optional[tuple] = None, fetch_one: bool = False, fetch_all: bool = False, commit: bool = False) -> Optional[Any | List[Any]]:
#     pass
#
# def close_connection(connection: Optional[mysql.connector.MySQLConnection], cursor: Optional[mysql.connector.cursor.MySQLCursor] = None) -> None:
#     pass 