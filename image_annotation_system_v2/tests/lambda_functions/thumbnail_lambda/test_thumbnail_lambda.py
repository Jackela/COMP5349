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

from lambda_functions.thumbnail_lambda.lambda_function import (
    lambda_handler,
    _download_image_from_s3,
    _generate_thumbnail,
    _upload_thumbnail_to_s3,
    _get_db_connection_lambda,
    _update_thumbnail_info_in_db
)
from web_app.utils.custom_exceptions import (
    COMP5349A2Error,
    S3InteractionError,
    DatabaseError,
    ImageProcessingError,
    ConfigurationError
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
            'S3_IMAGE_BUCKET': 'test-bucket',
            'THUMBNAIL_SIZE': '128x128',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-pass',
            'DB_NAME': 'test-db'
        })
        
        # Mock S3 download
        mock_s3_client = MagicMock()
        mock_response = {
            'Body': MagicMock(
                read=MagicMock(return_value=mock_image_bytes)
            )
        }
        mock_s3_client.get_object.return_value = mock_response
        mocker.patch('boto3.client', return_value=mock_s3_client)
        
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
        assert result['original_s3_key'] == 'test-image.jpg'
        assert result['thumbnail_s3_key'] == 'thumbnails/test-image.jpg'
        
        # Verify S3 download was called
        mock_s3_client.get_object.assert_called_once_with(
            Bucket='test-bucket',
            Key='test-image.jpg'
        )
        
        # Verify thumbnail generation was called with correct dimensions
        mock_generate_thumbnail_func.assert_called_once_with(
            mock_image_bytes,
            (128, 128),
            mock_lambda_context.aws_request_id
        )
        
        # Verify thumbnail upload was called
        mock_upload_thumbnail_func.assert_called_once_with(
            'test-bucket',
            'thumbnails/test-image.jpg',
            mock_thumbnail_io,
            mock_lambda_context.aws_request_id
        )
        
        # Verify DB update was called
        mock_update_thumbnail_info_func.assert_called_once_with(
            mock_db_connection,
            'test-image.jpg',
            'thumbnails/test-image.jpg',
            'completed',
            mock_lambda_context.aws_request_id
        )
        mock_get_db_connection_func.assert_called_once_with(mock_lambda_context.aws_request_id)

    def test_handler_skips_thumbnail_path_object(
        self, mocker, mock_s3_event_for_thumbnail, mock_lambda_context
    ):
        """Test that thumbnail objects are skipped."""
        # Arrange
        mocker.patch.dict(os.environ, {
            'S3_IMAGE_BUCKET': 'test-bucket',
            'THUMBNAIL_SIZE': '128x128'
        })
        
        # Act
        result = lambda_handler(mock_s3_event_for_thumbnail, mock_lambda_context)
        
        # Assert
        assert result['status'] == 'skipped'
        assert result['reason'] == 'thumbnail_object'
        assert result['s3_key'] == 'thumbnails/test-image.jpg'

    def test_handler_s3_download_failure_updates_db_and_raises(
        self, mocker, mock_s3_event, mock_lambda_context, mock_db_connection
    ):
        """Test S3 download failure updates DB status and raises error."""
        # Arrange
        mocker.patch.dict(os.environ, {
            'S3_IMAGE_BUCKET': 'test-bucket',
            'THUMBNAIL_SIZE': '128x128',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-pass',
            'DB_NAME': 'test-db'
        })
        
        # Mock S3 client to raise error
        mock_s3_client = MagicMock()
        mock_s3_client.get_object.side_effect = ClientError(
            error_response={'Error': {'Code': 'NoSuchKey', 'Message': 'Not found'}},
            operation_name='GetObject'
        )
        mocker.patch('boto3.client', return_value=mock_s3_client)
        
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
        
        assert "Failed to download image" in str(exc_info.value)
        assert exc_info.value.error_code == "S3_DOWNLOAD_FAILED"
        
        # Verify DB was updated with failure status
        mock_update_thumbnail_info_func.assert_called_once_with(
            mock_db_connection,
            'test-image.jpg',
            None,
            'failed',
            mock_lambda_context.aws_request_id
        )
        mock_get_db_connection_func.assert_called_once_with(mock_lambda_context.aws_request_id)

    def test_handler_image_processing_failure_updates_db_and_raises(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes, mock_db_connection
    ):
        """Test image processing failure updates DB status and raises error."""
        # Arrange
        mocker.patch.dict(os.environ, {
            'S3_IMAGE_BUCKET': 'test-bucket',
            'THUMBNAIL_SIZE': '128x128',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-pass',
            'DB_NAME': 'test-db'
        })
        
        # Mock S3 download
        mock_s3_client = MagicMock()
        mock_response = {
            'Body': MagicMock(
                read=MagicMock(return_value=mock_image_bytes)
            )
        }
        mock_s3_client.get_object.return_value = mock_response
        mocker.patch('boto3.client', return_value=mock_s3_client)
        
        # Mock thumbnail generation to raise error
        mock_generate_thumbnail_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._generate_thumbnail',
            side_effect=ImageProcessingError(
                "Failed to process image",
                error_code="PILLOW_PROCESSING_ERROR"
            )
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
        with pytest.raises(ImageProcessingError) as exc_info:
            lambda_handler(mock_s3_event, mock_lambda_context)
        
        assert "Failed to process image" in str(exc_info.value)
        assert exc_info.value.error_code == "PILLOW_PROCESSING_ERROR"
        
        # Verify DB was updated with failure status
        mock_update_thumbnail_info_func.assert_called_once_with(
            mock_db_connection,
            'test-image.jpg',
            None,
            'failed',
            mock_lambda_context.aws_request_id
        )
        mock_get_db_connection_func.assert_called_once_with(mock_lambda_context.aws_request_id)
        mock_generate_thumbnail_func.assert_called_once()

    def test_handler_s3_thumbnail_upload_failure_updates_db_and_raises(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes, mock_db_connection
    ):
        """Test thumbnail upload failure updates DB status and raises error."""
        # Arrange
        mocker.patch.dict(os.environ, {
            'S3_IMAGE_BUCKET': 'test-bucket',
            'THUMBNAIL_SIZE': '128x128',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-pass',
            'DB_NAME': 'test-db'
        })
        
        # Mock S3 download
        mock_s3_client = MagicMock()
        mock_response = {
            'Body': MagicMock(
                read=MagicMock(return_value=mock_image_bytes)
            )
        }
        mock_s3_client.get_object.return_value = mock_response
        mocker.patch('boto3.client', return_value=mock_s3_client)
        
        # Mock thumbnail generation
        mock_thumbnail_io = io.BytesIO(b"mock thumbnail content")
        mock_generate_thumbnail_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._generate_thumbnail',
            return_value=mock_thumbnail_io
        )
        
        # Mock thumbnail upload to raise error
        mock_upload_thumbnail_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._upload_thumbnail_to_s3',
            side_effect=S3InteractionError(
                "Failed to upload thumbnail",
                error_code="S3_UPLOAD_FAILED"
            )
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
        
        assert "Failed to upload thumbnail" in str(exc_info.value)
        assert exc_info.value.error_code == "S3_UPLOAD_FAILED"
        
        # Verify DB was updated with failure status
        mock_update_thumbnail_info_func.assert_called_once_with(
            mock_db_connection,
            'test-image.jpg',
            'thumbnails/test-image.jpg',
            'failed',
            mock_lambda_context.aws_request_id
        )
        mock_get_db_connection_func.assert_called_once_with(mock_lambda_context.aws_request_id)
        mock_generate_thumbnail_func.assert_called_once()
        mock_upload_thumbnail_func.assert_called_once()

    def test_handler_db_update_failure_raises_db_error_after_processing(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes, mock_db_connection
    ):
        """Test DB update failure after successful processing raises error."""
        # Arrange
        mocker.patch.dict(os.environ, {
            'S3_IMAGE_BUCKET': 'test-bucket',
            'THUMBNAIL_SIZE': '128x128',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-pass',
            'DB_NAME': 'test-db'
        })
        
        # Mock S3 download
        mock_s3_client = MagicMock()
        mock_response = {
            'Body': MagicMock(
                read=MagicMock(return_value=mock_image_bytes)
            )
        }
        mock_s3_client.get_object.return_value = mock_response
        mocker.patch('boto3.client', return_value=mock_s3_client)
        
        # Mock thumbnail generation
        mock_thumbnail_io = io.BytesIO(b"mock thumbnail content")
        mock_generate_thumbnail_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._generate_thumbnail',
            return_value=mock_thumbnail_io
        )
        
        # Mock thumbnail upload
        mock_upload_thumbnail_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._upload_thumbnail_to_s3'
        )
        
        # Mock DB connection and update to raise error
        mock_get_db_connection_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._get_db_connection_lambda',
            return_value=mock_db_connection
        )
        mock_update_thumbnail_info_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._update_thumbnail_info_in_db',
            side_effect=DatabaseError(
                "Failed to update database",
                error_code="DB_UPDATE_FAILED"
            )
        )
        
        # Act & Assert
        with pytest.raises(DatabaseError) as exc_info:
            lambda_handler(mock_s3_event, mock_lambda_context)
        
        assert "Failed to update database" in str(exc_info.value)
        assert exc_info.value.error_code == "DB_UPDATE_FAILED"
        # Verify that the processing functions were called
        mock_s3_client.get_object.assert_called_once()
        mock_generate_thumbnail_func.assert_called_once()
        mock_upload_thumbnail_func.assert_called_once()
        mock_get_db_connection_func.assert_called_once()
        mock_update_thumbnail_info_func.assert_called_once()

    def test_handler_invalid_thumbnail_size_env_uses_default_and_logs_warning(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes, mock_db_connection
    ):
        """Test invalid THUMBNAIL_SIZE environment variable uses default size."""
        # Arrange
        mocker.patch.dict(os.environ, {
            'S3_IMAGE_BUCKET': 'test-bucket',
            'THUMBNAIL_SIZE': 'invalid-size',  # Invalid format
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-pass',
            'DB_NAME': 'test-db'
        })
        
        # Mock S3 download
        mock_s3_client = MagicMock()
        mock_response = {
            'Body': MagicMock(
                read=MagicMock(return_value=mock_image_bytes)
            )
        }
        mock_s3_client.get_object.return_value = mock_response
        mocker.patch('boto3.client', return_value=mock_s3_client)
        
        # Mock thumbnail generation
        mock_thumbnail_io = io.BytesIO(b"mock thumbnail content")
        mock_generate_thumbnail_func = mocker.patch(
            'lambda_functions.thumbnail_lambda.lambda_function._generate_thumbnail',
            return_value=mock_thumbnail_io
        )
        
        # Mock thumbnail upload
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
        
        # Verify thumbnail generation was called with default dimensions (128,128)
        mock_generate_thumbnail_func.assert_called_once_with(
            mock_image_bytes,
            (128, 128),
            mock_lambda_context.aws_request_id
        )
        # Verify other calls
        mock_upload_thumbnail_func.assert_called_once()
        mock_get_db_connection_func.assert_called_once()
        mock_update_thumbnail_info_func.assert_called_once()

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
        """Test successful thumbnail info update in database."""
        # Arrange
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1  # 设置 rowcount 为整数
        mock_db_connection.cursor.return_value = mock_cursor
        
        # Act
        result = _update_thumbnail_info_in_db(
            mock_db_connection,
            'test-image.jpg',
            'thumbnails/test-image.jpg',
            'completed',
            'test-request-id'
        )
        
        # Assert
        assert result is True
        mock_cursor.execute.assert_called_once()
        mock_db_connection.commit.assert_called_once()

    def test_update_thumbnail_info_db_error_raises_db_error(
        self, mocker, mock_db_connection
    ):
        """Test database error during update raises DatabaseError."""
        # Arrange
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 0  # 设置 rowcount 为整数
        mock_cursor.execute.side_effect = mysql.connector.Error("Update failed")
        mock_db_connection.cursor.return_value = mock_cursor
        
        # Act & Assert
        with pytest.raises(DatabaseError) as exc_info:
            _update_thumbnail_info_in_db(
                mock_db_connection,
                'test-image.jpg',
                'thumbnails/test-image.jpg',
                'completed',
                'test-request-id'
            )
        
        assert "Database error while updating thumbnail info" in str(exc_info.value)
        assert exc_info.value.error_code == "DB_UPDATE_FAILED"