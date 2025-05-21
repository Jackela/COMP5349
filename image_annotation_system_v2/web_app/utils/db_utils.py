# db_utils.py - Database interaction utilities 
import os
import mysql.connector
from mysql.connector import errorcode # For specific error codes like ER_DUP_ENTRY
from typing import Optional, List, Dict, Any, Tuple
import datetime # Add if needed later
from .custom_exceptions import COMP5349A2Error, DatabaseError, ConfigurationError, InvalidInputError

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
    original_s3_key: str,
    request_id: Optional[str] = None # For logging context
) -> int:
    """
    Saves initial metadata for a newly uploaded image to the images table.
    Sets caption and thumbnail_s3_key to NULL and statuses to 'pending'.

    Args:
        db_conn: An active database connection object.
        original_s3_key: The unique S3 key for the original uploaded image.
                         This key must be unique in the 'images' table.
        request_id: Optional. The request ID for logging correlation.
                    (Note: Direct logging from this util is deferred to the caller)

    Raises:
        DatabaseError: If a database error occurs during the insert.
                       Specifically, if original_s3_key violates a UNIQUE constraint,
                       the error_code will be "DB_UNIQUE_VIOLATION".

    Returns:
        int: The auto-incremented ID of the newly inserted record.
    """
    cursor = None  # Initialize cursor to None for the finally block
    try:
        cursor = db_conn.cursor()
        
        # As per the schema.sql, original_s3_key is the primary identifier from S3.
        # uploaded_at, caption, thumbnail_s3_key, caption_status, thumbnail_status are the fields.
        # The schema.sql uses 'upload_timestamp' not 'uploaded_at'. Let's assume the table schema is:
        # id SERIAL PRIMARY KEY,
        # filename VARCHAR(255) NOT NULL,  <-- This field is not in the INSERT, assuming it's handled elsewhere or not mandatory at this stage
        # s3_key VARCHAR(1024) NOT NULL UNIQUE, (corresponds to original_s3_key)
        # thumbnail_s3_key VARCHAR(1024) UNIQUE,
        # upload_timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
        # tags TEXT[], <-- Not handled in this initial insert
        # annotations JSONB, <-- Not handled in this initial insert
        # -- The design doc mentions caption_status and thumbnail_status, which are not in schema.sql
        # -- For now, I will stick to the SQL in the prompt, which implies these status fields exist.
        # -- If they don't, the SQL will fail. The prompt's SQL is:
        # -- INSERT INTO images (original_s3_key, uploaded_at, caption, thumbnail_s3_key, caption_status, thumbnail_status)
        # -- VALUES (%s, CURRENT_TIMESTAMP, NULL, NULL, 'pending', 'pending')
        # -- I will adjust based on the provided schema.sql which is more concrete.
        # -- The schema provided uses s3_key for original_s3_key and upload_timestamp. No status fields yet.
        # -- Adapting to schema.sql: only s3_key (for original_s3_key) and filename are strictly NOT NULL.
        # -- Assuming filename is also passed or handled differently. The function only takes original_s3_key.
        # -- Given the function signature and purpose, it should only insert the S3 key and let defaults/NULLs apply.
        # -- However, the prompt SQL is very specific. I will follow the prompt's SQL INSERT structure,
        # -- assuming the table will be augmented with caption_status and thumbnail_status columns.

        sql_insert_image = """
        INSERT INTO images 
        (s3_key, upload_timestamp, filename, caption_status, thumbnail_status) 
        VALUES (%s, CURRENT_TIMESTAMP, %s, 'pending', 'pending')
        """
        # Assuming a placeholder for filename, as it's NOT NULL in schema but not in function args.
        # This will need clarification. For now, using original_s3_key as a placeholder for filename too.
        # This is a likely point of failure if filename cannot be derived from original_s3_key or is expected separately.
        # To make it runnable based on current info, will use original_s3_key for filename field for now.

        # Revised based on the user's provided SQL in the prompt, which takes precedence for this function's implementation
        # over direct schema interpretation if there are discrepancies for fields like 'uploaded_at' vs 'upload_timestamp'
        # or presence of status fields.
        # The user prompt for save_initial_image_meta explicitly states:
        # sql_insert_image = """ INSERT INTO images (original_s3_key, uploaded_at, caption, thumbnail_s3_key, caption_status, thumbnail_status) VALUES (%s, CURRENT_TIMESTAMP, NULL, NULL, 'pending', 'pending') """
        # This means the table 'images' is expected to have columns: original_s3_key, uploaded_at, caption, thumbnail_s3_key, caption_status, thumbnail_status.
        # The schema.sql provided earlier uses 's3_key' and 'upload_timestamp' and does not have status fields.
        # I will use the column names and structure as per the *function-specific SQL instruction* from the prompt.
        # This assumes the database schema will align with this specific insert statement for this function to work.

        sql_insert_image_from_prompt = """
        INSERT INTO images (original_s3_key, uploaded_at, caption, thumbnail_s3_key, caption_status, thumbnail_status) 
        VALUES (%s, CURRENT_TIMESTAMP, NULL, NULL, 'pending', 'pending')
        """
        # Parameter for the SQL query is just (original_s3_key,) as per the SQL structure.       
        cursor.execute(sql_insert_image_from_prompt, (original_s3_key,))
        db_conn.commit()
        new_id = cursor.lastrowid

        # Caller will handle logging if needed, for example:
        # if request_id:
        #     app.logger.info(f"[ReqID: {request_id}] Saved initial image meta for {original_s3_key}, new ID: {new_id}")
        # else:
        #     app.logger.info(f"Saved initial image meta for {original_s3_key}, new ID: {new_id}")
        
        if new_id is None:
            # This case should ideally not happen if auto-increment is working and commit was successful.
            # However, some DB configurations or specific scenarios (like ON DUPLICATE KEY UPDATE without returning ID)
            # might lead to this. For a simple INSERT, lastrowid should be populated.
            # Re-querying for the ID or raising an error might be options here if new_id can be None.
            # For now, assuming lastrowid is reliable for new inserts.
            raise DatabaseError(
                message=f"Failed to retrieve new ID after inserting metadata for {original_s3_key}. lastrowid was None.",
                error_code="DB_UPDATE_FAILED"
            )

        return new_id
        
    except mysql.connector.Error as e:
        # The calling code should handle logging of these re-raised exceptions.
        if e.errno == errorcode.ER_DUP_ENTRY:
            # Specific error for unique constraint violation
            raise DatabaseError(
                message=f"Duplicate entry for original_s3_key: {original_s3_key}. This image key already exists in the database.",
                error_code="DB_UNIQUE_VIOLATION",
                original_exception=e
            )
        else:
            # General database error for other issues
            raise DatabaseError(
                message=f"Failed to save initial image metadata for {original_s3_key}. Database error: {e.msg}",
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
        sql_select_all = (
            """
            SELECT id, original_s3_key, caption, thumbnail_s3_key, 
                   caption_status, thumbnail_status, uploaded_at 
            FROM images 
            ORDER BY uploaded_at DESC
            """
        )
        cursor.execute(sql_select_all)
        results = cursor.fetchall()
        return results
    except mysql.connector.Error as e:
        raise DatabaseError(
            message="Failed to retrieve images for gallery.",
            error_code="DB_UPDATE_FAILED",
            original_exception=e
        )
    finally:
        if cursor:
            cursor.close()

def update_caption_in_db(
    db_conn: mysql.connector.MySQLConnection,
    original_s3_key: str,
    caption_text: Optional[str],
    status: str,
    request_id: Optional[str] = None
) -> bool:
    """
    Updates the caption text and status for a given image identified by original_s3_key.

    Args:
        db_conn: An active database connection object.
        original_s3_key: The S3 key of the image record to update.
        caption_text: The caption text to set. Can be None if status is 'failed'
                      and no specific error message is to be stored in the caption field.
        status: The new caption status. Must be 'completed' or 'failed'.
        request_id: Optional. The request ID for logging correlation.

    Raises:
        InvalidInputError: If the provided status is not 'completed' or 'failed'.
        DatabaseError: If a database error occurs during the update.

    Returns:
        bool: True if a record was found and updated (i.e., rowcount > 0),
              False if no record was found with the given original_s3_key.
    """
    if status not in ('completed', 'failed'):
        # Logging by caller
        raise InvalidInputError(
            f"Invalid status parameter '{status}' for update_caption_in_db. Must be 'completed' or 'failed'."
        )

    cursor = None
    try:
        cursor = db_conn.cursor()
        sql_update_caption = (
            """
            UPDATE images 
            SET caption = %s, caption_status = %s 
            WHERE original_s3_key = %s
            """
        )
        cursor.execute(sql_update_caption, (caption_text, status, original_s3_key))
        db_conn.commit()
        affected_rows = cursor.rowcount
        return affected_rows > 0
    except mysql.connector.Error as e:
        raise DatabaseError(
            message=f"Failed to update caption for {original_s3_key}. DB Error: {e.msg}",
            original_exception=e
        )
    finally:
        if cursor:
            cursor.close()

def update_thumbnail_info_in_db(
    db_conn: mysql.connector.MySQLConnection,
    original_s3_key: str,
    thumbnail_s3_key: Optional[str],
    status: str,
    request_id: Optional[str] = None
) -> bool:
    """
    Updates the thumbnail S3 key and processing status for a given image
    identified by original_s3_key.

    Args:
        db_conn: An active database connection object.
        original_s3_key: The S3 key of the original image record to update.
        thumbnail_s3_key: The S3 key of the generated thumbnail. Should be None
                          if the status is 'failed'.
        status: The new thumbnail processing status. Must be 'completed' or 'failed'.
        request_id: Optional. The request ID for logging correlation.

    Raises:
        InvalidInputError: If the provided status is not 'completed' or 'failed'.
        DatabaseError: If a database error occurs during the update.

    Returns:
        bool: True if a record was found and updated (i.e., rowcount > 0),
              False if no record was found with the given original_s3_key.
    """
    if status not in ('completed', 'failed'):
        raise InvalidInputError(
            f"Invalid status parameter '{status}' for update_thumbnail_info_in_db. Must be 'completed' or 'failed'."
        )

    # If status is 'failed', ensure thumbnail_s3_key is None for consistency.
    if status == 'failed' and thumbnail_s3_key is not None:
        thumbnail_s3_key = None

    cursor = None
    try:
        cursor = db_conn.cursor()
        sql_update_thumbnail = (
            """
            UPDATE images 
            SET thumbnail_s3_key = %s, thumbnail_status = %s 
            WHERE original_s3_key = %s
            """
        )
        cursor.execute(sql_update_thumbnail, (thumbnail_s3_key, status, original_s3_key))
        db_conn.commit()
        affected_rows = cursor.rowcount
        return affected_rows > 0
    except mysql.connector.Error as e:
        raise DatabaseError(
            message=f"Failed to update thumbnail info for {original_s3_key}. DB Error: {e.msg}",
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