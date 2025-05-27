# Unit tests for lambda_functions.thumbnail_lambda.lambda_function 

import os
import io
import json
import pytest
from unittest.mock import MagicMock, patch
from PIL import Image, UnidentifiedImageError
import boto3
from botocore.exceptions import ClientError
import mysql.connector
import sys # Add sys import

# Adjust sys.path so that lambda_function.py can find custom_exceptions.py
lambda_function_dir_thumbnail = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lambda_functions', 'thumbnail_lambda'))
if lambda_function_dir_thumbnail not in sys.path:
    sys.path.insert(0, lambda_function_dir_thumbnail)

from lambda_functions.thumbnail_lambda.lambda_function import (
    lambda_handler,
    _download_image_from_s3,
    _generate_thumbnail,
    _upload_thumbnail_to_s3,
    _get_db_connection_lambda,
    _update_thumbnail_info_in_db
)
# custom_exceptions is now found because lambda_function_dir_thumbnail is in sys.path
# when lambda_function is imported.
from custom_exceptions import (
    COMP5349A2Error,
    S3InteractionError,
    DatabaseError,
    ImageProcessingError,
    ConfigurationError,
    InvalidInputError # Make sure all used exceptions are imported for type checking if needed
)

# --- Fixtures ---
@pytest.fixture
def mock_lambda_context():
    """Mock AWS Lambda context object."""
    context = MagicMock()
    context.aws_request_id = 'test-aws-request-id-123'
    return context

@pytest.fixture
def mock_s3_event():
    """Mock S3 event for a new image upload."""
    return {
        'Records': [{
            's3': {
                'bucket': {
                    'name': 'test-bucket'
                },
                'object': {
                    'key': 'test-image.jpg'
                }
            }
        }]
    }

@pytest.fixture
def mock_s3_event_for_thumbnail():
    """Mock S3 event for a thumbnail object (should be skipped)."""
    return {
        'Records': [{
            's3': {
                'bucket': {
                    'name': 'test-bucket'
                },
                'object': {
                    'key': 'thumbnails/test-image.jpg'
                }
            }
        }]
    }

@pytest.fixture
def mock_image_bytes():
    """Mock image bytes for testing."""
    return b"mock image content"

@pytest.fixture
def mock_db_connection():
    """Mock database connection."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn

@pytest.fixture
def sample_image_bytes_png_with_alpha():
    """Create a sample PNG image with alpha channel for testing."""
    img = Image.new('RGBA', (200, 200), (255, 0, 0, 128))
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return img_byte_arr.getvalue()

@pytest.fixture
def sample_image_bytes_jpg():
    """Create a sample JPG image for testing."""
    img = Image.new('RGB', (200, 200), (255, 0, 0))
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_byte_arr.seek(0)
    return img_byte_arr.getvalue()

# --- Test Lambda Handler ---
class TestLambdaHandler:
    def test_handler_success_thumbnail_generated_uploaded_db_updated(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes, mock_db_connection
    ):
        """Test successful thumbnail generation, upload, and DB update."""
        # Arrange
        mocker.patch.dict(os.environ, {
            # 'S3_IMAGE_BUCKET': 'test-bucket', # Source bucket comes from event
            'THUMBNAIL_BUCKET_NAME': 'test-thumbnail-bucket', # Target bucket for thumbnails
            'TARGET_WIDTH': '150',
            'TARGET_HEIGHT': '150',
            'THUMBNAIL_KEY_PREFIX': 'thumbs_prefix/',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-pass',
            'DB_NAME': 'test-db'
        })
        
        # Mock S3 download (using _download_image_from_s3 directly as it's cleaner)
        mock_download_s3_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._download_image_from_s3',
            return_value=mock_image_bytes
        )
        
        # Mock thumbnail generation
        mock_thumbnail_io = io.BytesIO(b"mock thumbnail content")
        mock_generate_thumbnail_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._generate_thumbnail',
            return_value=mock_thumbnail_io
        )
        
        # Mock S3 upload
        mock_upload_thumbnail_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._upload_thumbnail_to_s3'
        )
        
        # Mock DB connection and update
        mock_get_db_connection_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._get_db_connection_lambda',
            return_value=mock_db_connection
        )
        mock_update_thumbnail_info_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._update_thumbnail_info_in_db',
            return_value=True
        )
        
        # Act
        result = lambda_handler(mock_s3_event, mock_lambda_context)
        
        # Assert
        assert result['status'] == 'success'
        assert result['s3_key_original'] == 'test-image.jpg'
        assert result['s3_key_thumbnail'] == 'thumbs_prefix/test-image.jpg' # Based on new prefix logic
        
        # Verify S3 download was called
        mock_download_s3_func.assert_called_once_with(
            'test-bucket', # Source bucket from event
            'test-image.jpg',
            mock_lambda_context.aws_request_id
        )
        
        # Verify thumbnail generation was called with correct dimensions
        mock_generate_thumbnail_func.assert_called_once_with(
            mock_image_bytes,
            (150, 150), # From mocked env vars
            mock_lambda_context.aws_request_id
        )
        
        # Verify thumbnail upload was called
        mock_upload_thumbnail_func.assert_called_once_with(
            'test-thumbnail-bucket', # Target bucket from env var
            'thumbs_prefix/test-image.jpg', # Expected key with prefix
            mock_thumbnail_io,
            mock_lambda_context.aws_request_id
        )
        
        # Verify DB update was called
        mock_update_thumbnail_info_func.assert_called_once_with(
            db_conn=mock_db_connection, # Ensure db_conn is passed correctly
            filename='test-image.jpg', # Added filename
            s3_key_original='test-image.jpg',
            thumbnail_s3_key='thumbs_prefix/test-image.jpg',
            status='completed',
            aws_request_id=mock_lambda_context.aws_request_id
        )
        mock_get_db_connection_func.assert_called_once_with(mock_lambda_context.aws_request_id)

    def test_handler_skips_thumbnail_path_object(
        self, mocker, mock_s3_event_for_thumbnail, mock_lambda_context
    ):
        """Test that thumbnail objects are skipped based on default prefix."""
        # Arrange
        # No specific bucket env vars needed as it should skip before S3/DB ops
        # THUMBNAIL_KEY_PREFIX will use its default 'thumbnails/' if not set
        mocker.patch.dict(os.environ, {
            # Minimal env for parsing, though not strictly used if skipped early
            'TARGET_WIDTH': '128',
            'TARGET_HEIGHT': '128'
        })
        
        # Act
        result = lambda_handler(mock_s3_event_for_thumbnail, mock_lambda_context)
        
        # Assert
        assert result['status'] == 'skipped'
        assert result['reason'] == 'is_thumbnail_object' # Updated reason
        assert result['s3_key_original'] == 'thumbnails/test-image.jpg' # Key name in result

    def test_handler_skips_thumbnail_path_object_custom_prefix(
        self, mocker, mock_lambda_context
    ):
        """Test that thumbnail objects are skipped based on custom prefix."""
        # Arrange
        custom_prefix = 'custom_thumbs/'
        mock_s3_event_custom_thumb = {
            'Records': [{
                's3': {
                    'bucket': {
                        'name': 'test-bucket'
                    },
                    'object': {
                        'key': f'{custom_prefix}test-image.jpg'
                    }
                }
            }]
        }
        mocker.patch.dict(os.environ, {
            'THUMBNAIL_KEY_PREFIX': custom_prefix,
            'TARGET_WIDTH': '128',
            'TARGET_HEIGHT': '128'
        })
        
        # Act
        result = lambda_handler(mock_s3_event_custom_thumb, mock_lambda_context)
        
        # Assert
        assert result['status'] == 'skipped'
        assert result['reason'] == 'is_thumbnail_object'
        assert result['s3_key_original'] == f'{custom_prefix}test-image.jpg'

    def test_handler_s3_download_failure_updates_db_and_raises(
        self, mocker, mock_s3_event, mock_lambda_context, mock_db_connection
    ):
        """Test S3 download failure updates DB status and raises error."""
        # Arrange
        mocker.patch.dict(os.environ, {
            'THUMBNAIL_BUCKET_NAME': 'test-thumbnail-bucket',
            'TARGET_WIDTH': '128',
            'TARGET_HEIGHT': '128',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-pass',
            'DB_NAME': 'test-db'
        })
        
        # Mock _download_image_from_s3 to raise error
        s3_error = S3InteractionError("Failed to download", error_code="S3_DOWNLOAD_ERROR")
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._download_image_from_s3',
            side_effect=s3_error
        )
        
        # Mock DB connection and update
        mock_get_db_connection_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._get_db_connection_lambda',
            return_value=mock_db_connection
        )
        mock_update_thumbnail_info_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._update_thumbnail_info_in_db',
            return_value=True
        )
        
        # Act & Assert
        with pytest.raises(S3InteractionError) as exc_info:
            lambda_handler(mock_s3_event, mock_lambda_context)
        
        assert exc_info.value.message == "Failed to download"
        assert exc_info.value.error_code == "S3_DOWNLOAD_ERROR"
        
        # Verify DB was updated with failure status
        mock_update_thumbnail_info_func.assert_called_once_with(
            db_conn=mock_db_connection,
            filename='test-image.jpg', # Added filename
            s3_key_original='test-image.jpg',
            thumbnail_s3_key=None, # Should be None on failure before upload key generation
            status='failed',
            aws_request_id=mock_lambda_context.aws_request_id
        )
        mock_get_db_connection_func.assert_called_once_with(mock_lambda_context.aws_request_id)

    def test_handler_image_processing_failure_updates_db_and_raises(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes, mock_db_connection
    ):
        """Test image processing failure updates DB status and raises error."""
        # Arrange
        mocker.patch.dict(os.environ, {
            'THUMBNAIL_BUCKET_NAME': 'test-thumbnail-bucket',
            'TARGET_WIDTH': '128',
            'TARGET_HEIGHT': '128',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-pass',
            'DB_NAME': 'test-db'
        })
        
        mock_download_s3_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._download_image_from_s3',
            return_value=mock_image_bytes
        )
        
        img_proc_error = ImageProcessingError("Pillow error", error_code="PILLOW_ERROR")
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._generate_thumbnail',
            side_effect=img_proc_error
        )
        
        mock_get_db_connection_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._get_db_connection_lambda',
            return_value=mock_db_connection
        )
        mock_update_thumbnail_info_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._update_thumbnail_info_in_db',
            return_value=True
        )
        
        # Act & Assert
        with pytest.raises(ImageProcessingError) as exc_info:
            lambda_handler(mock_s3_event, mock_lambda_context)
        
        assert "Pillow error" in str(exc_info.value)
        assert exc_info.value.error_code == "PILLOW_ERROR"
        
        mock_update_thumbnail_info_func.assert_called_once_with(
            db_conn=mock_db_connection,
            filename='test-image.jpg', # Added filename
            s3_key_original='test-image.jpg',
            thumbnail_s3_key=None,
            status='failed',
            aws_request_id=mock_lambda_context.aws_request_id
        )

    def test_handler_s3_thumbnail_upload_failure_updates_db_and_raises(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes, mock_db_connection
    ):
        """Test S3 thumbnail upload failure updates DB status and raises error."""
        # Arrange
        mocker.patch.dict(os.environ, {
            'THUMBNAIL_BUCKET_NAME': 'test-thumbnail-bucket',
            'TARGET_WIDTH': '128',
            'TARGET_HEIGHT': '128',
            'THUMBNAIL_KEY_PREFIX': 'thumbnails/',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-pass',
            'DB_NAME': 'test-db'
        })
        
        mock_download_s3_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._download_image_from_s3',
            return_value=mock_image_bytes
        )
        mock_thumbnail_io = io.BytesIO(b"mock thumbnail content")
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._generate_thumbnail',
            return_value=mock_thumbnail_io
        )
        
        s3_upload_error = S3InteractionError("Upload failed", error_code="S3_UPLOAD_ERROR")
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._upload_thumbnail_to_s3',
            side_effect=s3_upload_error
        )
        
        mock_get_db_connection_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._get_db_connection_lambda',
            return_value=mock_db_connection
        )
        mock_update_thumbnail_info_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._update_thumbnail_info_in_db',
            return_value=True
        )
        
        # Act & Assert
        with pytest.raises(S3InteractionError) as exc_info:
            lambda_handler(mock_s3_event, mock_lambda_context)
        
        assert "Upload failed" in str(exc_info.value)
        assert exc_info.value.error_code == "S3_UPLOAD_ERROR"
        
        # Even if upload fails, the key would have been generated
        expected_thumb_key = 'thumbnails/test-image.jpg' 
        mock_update_thumbnail_info_func.assert_called_once_with(
            db_conn=mock_db_connection,
            filename='test-image.jpg', # Added filename
            s3_key_original='test-image.jpg',
            thumbnail_s3_key=None, # On S3 upload failure, this should be None for DB
            status='failed',
            aws_request_id=mock_lambda_context.aws_request_id
        )

    def test_handler_db_update_failure_raises_db_error_after_processing(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes, mock_db_connection
    ):
        """Test DB update failure after successful processing raises DBError."""
        # Arrange
        mocker.patch.dict(os.environ, {
            'THUMBNAIL_BUCKET_NAME': 'test-thumbnail-bucket',
            'TARGET_WIDTH': '128',
            'TARGET_HEIGHT': '128',
            'THUMBNAIL_KEY_PREFIX': 'thumbnails/',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-pass',
            'DB_NAME': 'test-db'
        })

        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._download_image_from_s3',
            return_value=mock_image_bytes
        )
        mock_thumbnail_io = io.BytesIO(b"mock thumbnail content")
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._generate_thumbnail',
            return_value=mock_thumbnail_io
        )
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._upload_thumbnail_to_s3'
        )
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._get_db_connection_lambda',
            return_value=mock_db_connection
        )
        db_update_error = DatabaseError("DB update failed", error_code="DB_UPDATE_ERROR")
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._update_thumbnail_info_in_db',
            side_effect=db_update_error
        )

        # Act & Assert
        with pytest.raises(DatabaseError) as exc_info:
            lambda_handler(mock_s3_event, mock_lambda_context)
        
        assert "DB update failed" in str(exc_info.value)
        assert exc_info.value.error_code == "DB_UPDATE_ERROR"

    def test_handler_db_connection_failure_before_update_raises_db_error(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes
    ):
        """Test DB connection failure before update raises DBError."""
        # Arrange
        mocker.patch.dict(os.environ, {
            'THUMBNAIL_BUCKET_NAME': 'test-thumbnail-bucket',
            'TARGET_WIDTH': '128',
            'TARGET_HEIGHT': '128',
            'THUMBNAIL_KEY_PREFIX': 'thumbnails/',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-pass',
            'DB_NAME': 'test-db'
        })
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._download_image_from_s3',
            return_value=mock_image_bytes
        )
        mock_thumbnail_io = io.BytesIO(b"mock thumbnail content")
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._generate_thumbnail',
            return_value=mock_thumbnail_io
        )
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._upload_thumbnail_to_s3'
        )
        db_conn_error = DatabaseError("DB conn failed", error_code="DB_CONN_FAIL_ERROR")
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._get_db_connection_lambda',
            side_effect=db_conn_error
        )
        mock_update_db = mocker.patch('lambda_functions.thumbnail_lambda.lambda_function._update_thumbnail_info_in_db')

        # Act & Assert
        with pytest.raises(DatabaseError) as exc_info:
            lambda_handler(mock_s3_event, mock_lambda_context)
        
        assert "DB conn failed" in str(exc_info.value)
        assert exc_info.value.error_code == "DB_CONN_FAIL_ERROR"
        mock_update_db.assert_not_called() # Ensure update is not called if connection fails

    def test_handler_invalid_thumbnail_size_env_uses_default_and_logs_warning(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes, mock_db_connection
    ):
        """Test invalid THUMBNAIL_SIZE format uses default and logs warning."""
        # Arrange
        mocker.patch.dict(os.environ, {
            'THUMBNAIL_BUCKET_NAME': 'test-thumbnail-bucket',
            'TARGET_WIDTH': 'invalid', # Invalid width
            'TARGET_HEIGHT': '150',
            'THUMBNAIL_KEY_PREFIX': 'thumbnails/',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-pass',
            'DB_NAME': 'test-db'
        })
        
        mock_download_s3_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._download_image_from_s3',
            return_value=mock_image_bytes
        )
        mock_thumbnail_io = io.BytesIO(b"mock thumbnail content")
        mock_generate_thumbnail_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._generate_thumbnail',
            return_value=mock_thumbnail_io
        )
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._upload_thumbnail_to_s3'
        )
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._get_db_connection_lambda',
            return_value=mock_db_connection
        )
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._update_thumbnail_info_in_db',
            return_value=True
        )
        mock_logger_warning = mocker.patch('lambda_functions.thumbnail_lambda.lambda_function.logger.warning')
        
        # Act
        lambda_handler(mock_s3_event, mock_lambda_context)
        
        # Assert
        # Check that _generate_thumbnail was called with default dimensions (128, 128)
        mock_generate_thumbnail_func.assert_called_once_with(
            mock_image_bytes,
            (128, 128), 
            mock_lambda_context.aws_request_id
        )
        mock_logger_warning.assert_any_call(
            "Invalid TARGET_WIDTH ('invalid') or TARGET_HEIGHT ('150'). Using default 128x128.",
            extra={'request_id': mock_lambda_context.aws_request_id}
        )

    def test_handler_missing_thumbnail_bucket_name_uses_source_bucket_and_logs_warning(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes, mock_db_connection
    ):
        """Test missing THUMBNAIL_BUCKET_NAME uses source bucket and logs warning."""
        # Arrange
        # Ensure THUMBNAIL_BUCKET_NAME is NOT in environ
        env_vars = {
            'TARGET_WIDTH': '128',
            'TARGET_HEIGHT': '128',
            'THUMBNAIL_KEY_PREFIX': 'thumbnails/',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-pass',
            'DB_NAME': 'test-db'
        }
        if 'THUMBNAIL_BUCKET_NAME' in env_vars:
            del env_vars['THUMBNAIL_BUCKET_NAME']
        mocker.patch.dict(os.environ, env_vars, clear=True) # Clear to ensure it's not set
        # Re-patch the essential ones for the test to run further if this was the only config issue.
        mocker.patch.dict(os.environ, env_vars) 

        mock_download_s3_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._download_image_from_s3',
            return_value=mock_image_bytes
        )
        mock_thumbnail_io = io.BytesIO(b"mock thumbnail content")
        mock_generate_thumbnail_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._generate_thumbnail',
            return_value=mock_thumbnail_io
        )
        mock_upload_thumbnail_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._upload_thumbnail_to_s3'
        )
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._get_db_connection_lambda',
            return_value=mock_db_connection
        )
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._update_thumbnail_info_in_db',
            return_value=True
        )
        mock_logger_warning = mocker.patch('lambda_functions.thumbnail_lambda.lambda_function.logger.warning')

        # Act
        lambda_handler(mock_s3_event, mock_lambda_context)

        # Assert
        # Check that _upload_thumbnail_to_s3 was called with source bucket name
        source_bucket_from_event = mock_s3_event['Records'][0]['s3']['bucket']['name']
        mock_upload_thumbnail_func.assert_called_once_with(
            source_bucket_from_event, # Should default to source bucket
            'thumbnails/test-image.jpg',
            mock_thumbnail_io,
            mock_lambda_context.aws_request_id
        )
        mock_logger_warning.assert_any_call(
            f"THUMBNAIL_BUCKET_NAME not set. Defaulting to source bucket: {source_bucket_from_event}",
            extra={'request_id': mock_lambda_context.aws_request_id}
        )

    def test_handler_unexpected_error_during_processing_updates_db_and_raises_comp5349a2error(
        self, mocker, mock_s3_event, mock_lambda_context, mock_db_connection
    ):
        """Test an unexpected error during processing is caught, DB is updated, and COMP5349A2Error is raised."""
        # Arrange
        mocker.patch.dict(os.environ, {
            'THUMBNAIL_BUCKET_NAME': 'test-thumbnail-bucket',
            'TARGET_WIDTH': '128',
            'TARGET_HEIGHT': '128',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-pass',
            'DB_NAME': 'test-db'
        })

        unexpected_err = Exception("Something totally unexpected!")
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._download_image_from_s3',
            side_effect=unexpected_err # Error during download for example
        )
        mock_get_db_connection_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._get_db_connection_lambda',
            return_value=mock_db_connection
        )
        mock_update_thumbnail_info_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._update_thumbnail_info_in_db'
        )

        # Act & Assert
        with pytest.raises(COMP5349A2Error) as exc_info:
            lambda_handler(mock_s3_event, mock_lambda_context)

        assert "Unexpected error during thumbnail generation" in exc_info.value.message
        assert exc_info.value.error_code == 'THUMBNAIL_UNEXPECTED_ERROR'
        assert exc_info.value.original_exception == unexpected_err

        mock_update_thumbnail_info_func.assert_called_once_with(
            db_conn=mock_db_connection,
            filename='test-image.jpg', # Added filename
            s3_key_original='test-image.jpg',
            thumbnail_s3_key=None,
            status='failed',
            aws_request_id=mock_lambda_context.aws_request_id
        )

    def test_handler_db_error_after_processing_error_logs_and_raises_original_processing_error(
        self, mocker, mock_s3_event, mock_lambda_context, mock_db_connection
    ):
        """Test if a DB error occurs after a processing error, the original processing error is raised."""
        # Arrange
        mocker.patch.dict(os.environ, {
            'THUMBNAIL_BUCKET_NAME': 'test-thumbnail-bucket',
            'TARGET_WIDTH': '128',
            'TARGET_HEIGHT': '128',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-pass',
            'DB_NAME': 'test-db'
        })

        processing_err = ImageProcessingError("Pillow error", error_code="PILLOW_ERROR")
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._download_image_from_s3',
            return_value=b"some bytes" # Assume download is fine
        )
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._generate_thumbnail',
            side_effect=processing_err # Error during generation
        )

        db_conn_err = DatabaseError("DB connection failed for update", error_code="DB_CONN_UPDATE_FAIL")
        mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._get_db_connection_lambda',
            side_effect=db_conn_err # DB connection for status update fails
        )
        mock_update_db = mocker.patch('lambda_functions.thumbnail_lambda.lambda_function._update_thumbnail_info_in_db')
        mock_logger_warning = mocker.patch('lambda_functions.thumbnail_lambda.lambda_function.logger.warning')

        # Act & Assert
        with pytest.raises(ImageProcessingError) as exc_info:
            lambda_handler(mock_s3_event, mock_lambda_context)

        assert exc_info.value == processing_err # Original processing error should be raised
        mock_update_db.assert_not_called()
        # Check that the DB error was logged as a warning
        expected_log_message_part_db_error = f"Database-related error while updating status for 'test-image.jpg': {db_conn_err.message}"
        expected_log_message_part_original_error = f"Original processing error for 'test-image.jpg' occurred. Subsequent DB error: {db_conn_err.message}"
        
        # Check if the specific warning log about subsequent DB error occurred
        found_subsequent_db_error_log = False
        for call_args in mock_logger_warning.call_args_list:
            logged_message = call_args[0][0]
            if expected_log_message_part_original_error in logged_message:
                found_subsequent_db_error_log = True
                break
        assert found_subsequent_db_error_log, f"Expected log message part '{expected_log_message_part_original_error}' not found in warnings."

        # Also check that the initial DB connection error (which is now a warning context) was logged at warning level
        # This part might be redundant if the above check for the combined message is sufficient.
        # However, the lambda code logs the db_e.message directly first at ERROR if it's the primary error,
        # then logs the specific warning if there was a prior processing_exception.
        # Let's refine to check for the warning log more directly as per lambda logic.
        mock_logger_warning.assert_any_call(
            expected_log_message_part_original_error,
            extra={'request_id': mock_lambda_context.aws_request_id}
        )

# --- Test Helper Functions ---
class TestGenerateThumbnail:
    def test_generate_thumbnail_success_jpeg_output(
        self, mocker, sample_image_bytes_png_with_alpha
    ):
        """Test successful thumbnail generation from PNG with alpha channel."""
        # Arrange
        mock_img = MagicMock()
        mock_img.mode = 'P'
        mock_img.size = (200, 200)
        mock_img.info = {}
        
        # Mock Image.open to return our mock image
        mocker.patch('PIL.Image.open', return_value=mock_img)
        
        # Act
        result = _generate_thumbnail(
            sample_image_bytes_png_with_alpha,
            (128, 128),
            'test-request-id'
        )
        
        # Assert
        assert isinstance(result, io.BytesIO)
        mock_img.convert.assert_called_once_with('RGB')
        
        # Get the mock object returned by mock_img.convert('RGB')
        converted_mock_img = mock_img.convert.return_value
        
        converted_mock_img.thumbnail.assert_called_once_with((128, 128), Image.Resampling.LANCZOS)
        
        # Verify save was called on the converted image, with JPEG format
        converted_mock_img.save.assert_called_once()
        save_args = converted_mock_img.save.call_args[1]
        assert save_args.get('format') == 'JPEG'

    def test_generate_thumbnail_success_no_alpha_conversion(
        self, mocker, sample_image_bytes_jpg
    ):
        """Test successful thumbnail generation from JPG (no alpha conversion needed)."""
        # Arrange
        mock_img = MagicMock()
        mock_img.mode = 'RGB'
        mock_img.size = (200, 200)
        
        # Mock Image.open to return our mock image
        mocker.patch('PIL.Image.open', return_value=mock_img)
        
        # Act
        result = _generate_thumbnail(
            sample_image_bytes_jpg,
            (128, 128),
            'test-request-id'
        )
        
        # Assert
        assert isinstance(result, io.BytesIO)
        mock_img.convert.assert_not_called()  # No conversion needed for RGB
        mock_img.thumbnail.assert_called_once_with((128, 128), Image.Resampling.LANCZOS)
        mock_img.save.assert_called_once()
        # Verify save was called with JPEG format
        save_args = mock_img.save.call_args[1]
        assert save_args.get('format') == 'JPEG'

    def test_generate_thumbnail_unidentified_image_error_raises_image_processing_error(
        self, mocker
    ):
        """Test UnidentifiedImageError is properly wrapped in ImageProcessingError."""
        # Arrange
        mocker.patch('PIL.Image.open', side_effect=UnidentifiedImageError())
        
        # Act & Assert
        with pytest.raises(ImageProcessingError) as exc_info:
            _generate_thumbnail(
                b"invalid image data",
                (128, 128),
                'test-request-id'
            )
        
        assert "Cannot identify image file" in str(exc_info.value)
        assert exc_info.value.error_code == "INVALID_IMAGE_FORMAT"

    def test_generate_thumbnail_other_pillow_error_raises_image_processing_error(
        self, mocker
    ):
        """Test other Pillow errors are properly wrapped in ImageProcessingError."""
        # Arrange
        mock_img = MagicMock()
        mock_img.mode = 'P'
        mock_img.info = {}

        mock_converted_img = MagicMock()
        mock_converted_img.thumbnail.side_effect = Exception("Pillow error")
        mock_img.convert.return_value = mock_converted_img

        mocker.patch('PIL.Image.open', return_value=mock_img)
        
        # Act & Assert
        with pytest.raises(ImageProcessingError) as exc_info:
            _generate_thumbnail(
                b"valid image data",
                (128, 128),
                'test-request-id'
            )
        
        assert "Pillow processing error: Pillow error" in str(exc_info.value)
        assert exc_info.value.error_code == "PILLOW_PROCESSING_ERROR"

class TestUploadThumbnailToS3:
    def test_upload_success(self, mocker):
        """Test successful thumbnail upload to S3."""
        # Arrange
        mock_s3_client = MagicMock()
        mocker.patch('boto3.client', return_value=mock_s3_client)
        
        thumbnail_io = io.BytesIO(b"mock thumbnail content")
        
        # Act
        _upload_thumbnail_to_s3(
            'test-bucket',
            'thumbnails/test-image.jpg',
            thumbnail_io,
            'test-request-id'
        )
        
        # Assert
        mock_s3_client.upload_fileobj.assert_called_once()
        
        args, kwargs = mock_s3_client.upload_fileobj.call_args
        
        # Assert positional arguments: Bucket (args[1]), Key (args[2])
        # Fileobj (args[0]) is thumbnail_io, which we can also assert if needed.
        assert args[1] == 'test-bucket'  # Bucket
        assert args[2] == 'thumbnails/test-image.jpg' # Key
        
        # Assert ExtraArgs from keyword arguments
        assert kwargs['ExtraArgs']['ContentType'] == 'image/jpeg'

    def test_upload_s3_clienterror_raises_s3_interaction_error(self, mocker):
        """Test S3 ClientError is properly wrapped in S3InteractionError."""
        # Arrange
        mock_s3_client = MagicMock()
        mock_s3_client.upload_fileobj.side_effect = ClientError(
            error_response={'Error': {'Code': 'AccessDenied', 'Message': 'Access denied'}},
            operation_name='UploadFileobj'
        )
        mocker.patch('boto3.client', return_value=mock_s3_client)
        
        thumbnail_io = io.BytesIO(b"mock thumbnail content")
        
        # Act & Assert
        with pytest.raises(S3InteractionError) as exc_info:
            _upload_thumbnail_to_s3(
                'test-bucket',
                'thumbnails/test-image.jpg',
                thumbnail_io,
                'test-request-id'
            )
        
        assert "Failed to upload thumbnail" in str(exc_info.value)
        assert exc_info.value.error_code == "S3_UPLOAD_FAILED"

class TestDownloadImageFromS3:
    def test_download_success_returns_bytes(self, mocker):
        """Test successful image download from S3."""
        # Arrange
        mock_s3_client = MagicMock()
        mock_response = {
            'Body': MagicMock(
                read=MagicMock(return_value=b"mock image content")
            )
        }
        mock_s3_client.get_object.return_value = mock_response
        mocker.patch('boto3.client', return_value=mock_s3_client)
        
        # Act
        result = _download_image_from_s3(
            'test-bucket',
            'test-image.jpg',
            'test-request-id'
        )
        
        # Assert
        assert result == b"mock image content"
        mock_s3_client.get_object.assert_called_once_with(
            Bucket='test-bucket',
            Key='test-image.jpg'
        )

    def test_download_s3_clienterror_raises_s3_interaction_error(self, mocker):
        """Test S3 ClientError is properly wrapped in S3InteractionError."""
        # Arrange
        mock_s3_client = MagicMock()
        mock_s3_client.get_object.side_effect = ClientError(
            error_response={'Error': {'Code': 'NoSuchKey', 'Message': 'Not found'}},
            operation_name='GetObject'
        )
        mocker.patch('boto3.client', return_value=mock_s3_client)
        
        # Act & Assert
        with pytest.raises(S3InteractionError) as exc_info:
            _download_image_from_s3(
                'test-bucket',
                'test-image.jpg',
                'test-request-id'
            )
        
        assert "Failed to download image" in str(exc_info.value)
        assert exc_info.value.error_code == "S3_DOWNLOAD_FAILED"

class TestGetDBConnectionLambda:
    def test_get_db_connection_success(self, mocker):
        """Test successful database connection."""
        # Arrange
        mock_conn = MagicMock()
        mocker.patch.dict(os.environ, {
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-password',
            'DB_NAME': 'test-db'
        })
        mocker.patch('mysql.connector.connect', return_value=mock_conn)
        
        # Act
        result = _get_db_connection_lambda('test-request-id')
        
        # Assert
        assert result == mock_conn
        mysql.connector.connect.assert_called_once_with(
            host='test-host',
            user='test-user',
            password='test-password',
            database='test-db',
            port=3306
        )

    def test_get_db_connection_missing_env_vars_raises_config_error(self, mocker):
        """Test missing environment variables raises ConfigurationError."""
        # Arrange
        mocker.patch.dict(os.environ, {}, clear=True)
        
        # Act & Assert
        with pytest.raises(ConfigurationError) as exc_info:
            _get_db_connection_lambda('test-request-id')
        
        assert "Missing required database configuration" in str(exc_info.value)

    def test_get_db_connection_failure_raises_db_error(self, mocker):
        """Test connection failure raises DatabaseError."""
        # Arrange
        mocker.patch.dict(os.environ, {
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-password',
            'DB_NAME': 'test-db'
        })
        mocker.patch(
            'mysql.connector.connect',
            side_effect=mysql.connector.Error("Connection failed")
        )
        
        # Act & Assert
        with pytest.raises(DatabaseError) as exc_info:
            _get_db_connection_lambda('test-request-id')
        
        assert "Failed to connect to database" in str(exc_info.value)
        assert exc_info.value.error_code == "DB_CONNECTION_FAILED"

class TestUpdateThumbnailInfoInDB:
    def test_update_thumbnail_info_success(self, mocker, mock_db_connection):
        """Test successful thumbnail info upsert in database."""
        # Arrange
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_db_connection.cursor.return_value = mock_cursor

        # Act
        result = _update_thumbnail_info_in_db(
            db_conn=mock_db_connection,
            filename='test-image.jpg',
            s3_key_original='test-image.jpg',
            thumbnail_s3_key='thumbnails/test-image.jpg',
            status='completed',
            aws_request_id='test-request-id'
        )
        assert result is True
        mock_cursor.execute.assert_called_once_with(
            mocker.ANY, # SQL string
            ('test-image.jpg', 'test-image.jpg', 'thumbnails/test-image.jpg', 'completed')
        )
        mock_db_connection.commit.assert_called_once()

    def test_update_thumbnail_info_no_rows_affected_returns_false(self, mocker, mock_db_connection):
        """Test upsert with no rows affected (data identical) returns False and logs warning."""
        # Arrange
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 0 # Simulate no rows affected / data was identical
        mock_db_connection.cursor.return_value = mock_cursor
        mock_logger_warning = mocker.patch('lambda_functions.thumbnail_lambda.lambda_function.logger.warning')

        # Act
        result = _update_thumbnail_info_in_db(
            db_conn=mock_db_connection,
            filename='test-image.jpg',
            s3_key_original='test-image.jpg',
            thumbnail_s3_key='thumbnails/test-image.jpg',
            status='completed',
            aws_request_id='test-request-id'
        )

        # Assert
        assert result is False
        mock_logger_warning.assert_called_once()
        assert "UPSERT operation for test-image.jpg did not affect any rows" in mock_logger_warning.call_args[0][0]
        mock_db_connection.commit.assert_called_once() # Commit should still be called

    def test_update_thumbnail_info_db_error_raises_db_error(
        self, mocker, mock_db_connection
    ):
        """Test database error during upsert raises DatabaseError."""
        # Arrange
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = mysql.connector.Error("UPSERT failed")
        mock_db_connection.cursor.return_value = mock_cursor
        mock_db_connection.commit.side_effect = mysql.connector.Error("Commit also failed after execute error") # Optional: test commit error too

        # Act & Assert
        with pytest.raises(DatabaseError) as exc_info:
            _update_thumbnail_info_in_db(
                db_conn=mock_db_connection,
                filename='test-image.jpg',
                s3_key_original='test-image.jpg',
                thumbnail_s3_key='thumbnails/test-image.jpg',
                status='completed',
                aws_request_id='test-request-id'
            )
        assert "Database UPSERT error for thumbnail info: UPSERT failed" in str(exc_info.value)
        assert exc_info.value.error_code == 'DB_UPSERT_FAILED'
        # db_conn.commit() might not be called if execute fails, or it might. 
        # Depending on where the actual commit is in the try block of the original function.
        # Given the original function, commit is after execute, so if execute fails, commit isn't called.
        mock_db_connection.commit.assert_not_called() 

    def test_update_thumbnail_info_invalid_status_raises_invalid_input_error(
        self, mocker, mock_db_connection
    ):
        """Test invalid status raises InvalidInputError."""
        with pytest.raises(InvalidInputError) as exc_info:
            _update_thumbnail_info_in_db(
                db_conn=mock_db_connection,
                filename='test-image.jpg',
                s3_key_original='test-image.jpg',
                thumbnail_s3_key='thumbnails/test-image.jpg',
                status='processing',  # Invalid status
                aws_request_id='test-request-id'
            )
        assert "Invalid status 'processing'." in str(exc_info.value)
        assert exc_info.value.error_code == 'INVALID_STATUS'