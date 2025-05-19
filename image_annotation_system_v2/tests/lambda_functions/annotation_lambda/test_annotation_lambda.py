# Unit tests for lambda_functions.annotation_lambda.lambda_function 

import os
import io
import json
import pytest
from unittest.mock import patch, MagicMock, call
from botocore.exceptions import ClientError
import mysql.connector

from lambda_functions.annotation_lambda.lambda_function import (
    lambda_handler,
    _download_image_from_s3,
    _call_gemini_api,
    _get_db_connection_lambda,
    _update_caption_in_db
)
from web_app.utils.custom_exceptions import (
    S3InteractionError,
    GeminiAPIError,
    DatabaseError,
    ConfigurationError,
    COMP5349A2Error
)

# --- Fixtures ---
@pytest.fixture
def mock_lambda_context():
    """Create a mock Lambda context object."""
    context = MagicMock()
    context.aws_request_id = "test-aws-request-id-123"
    return context

@pytest.fixture
def mock_s3_event():
    """Create a sample S3 event for testing."""
    return {
        "Records": [{
            "s3": {
                "bucket": {
                    "name": "test-image-bucket"
                },
                "object": {
                    "key": "uploads/test-image.jpg"
                }
            }
        }]
    }

@pytest.fixture
def mock_s3_event_for_thumbnail():
    """Create a sample S3 event for a thumbnail object."""
    event = mock_s3_event()
    event["Records"][0]["s3"]["object"]["key"] = "thumbnails/test-image.jpg"
    return event

@pytest.fixture
def mock_image_bytes():
    """Create mock image bytes for testing."""
    return b"mock image content"

@pytest.fixture
def mock_db_connection():
    """Create a mock database connection."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    return conn

# --- Test Lambda Handler ---
class TestLambdaHandler:
    def test_handler_success_caption_generated_and_db_updated(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes, mock_db_connection
    ):
        """Test successful caption generation and database update."""
        # Arrange
        mock_caption = "A beautiful sunset over mountains"
        
        # Mock environment variables
        mocker.patch.dict(os.environ, {
            'GEMINI_API_KEY': 'test-api-key',
            'GEMINI_MODEL_NAME': 'gemini-pro-vision',
            'GEMINI_PROMPT': 'Describe this image',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-password',
            'DB_NAME': 'test-db'
        })
        
        # Mock helper functions
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._download_image_from_s3',
            return_value=mock_image_bytes
        )
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._call_gemini_api',
            return_value=mock_caption
        )
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._get_db_connection_lambda',
            return_value=mock_db_connection
        )
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._update_caption_in_db',
            return_value=True
        )
        
        # Act
        result = lambda_handler(mock_s3_event, mock_lambda_context)
        
        # Assert
        assert result == {
            'status': 'success',
            's3_key': 'uploads/test-image.jpg',
            'caption_length': len(mock_caption)
        }
        
        # Verify helper function calls
        _download_image_from_s3.assert_called_once_with(
            'test-image-bucket',
            'uploads/test-image.jpg',
            'test-aws-request-id-123'
        )
        _call_gemini_api.assert_called_once_with(
            mock_image_bytes,
            'test-aws-request-id-123'
        )
        _get_db_connection_lambda.assert_called_once_with('test-aws-request-id-123')
        _update_caption_in_db.assert_called_once_with(
            mock_db_connection,
            'uploads/test-image.jpg',
            mock_caption,
            'completed',
            'test-aws-request-id-123'
        )

    def test_handler_skips_thumbnail_object(
        self, mocker, mock_s3_event_for_thumbnail, mock_lambda_context
    ):
        """Test that thumbnail objects are skipped."""
        # Arrange
        mock_download = mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._download_image_from_s3'
        )
        mock_gemini = mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._call_gemini_api'
        )
        
        # Act
        result = lambda_handler(mock_s3_event_for_thumbnail, mock_lambda_context)
        
        # Assert
        assert result == {
            'status': 'skipped',
            'reason': 'thumbnail_object'
        }
        mock_download.assert_not_called()
        mock_gemini.assert_not_called()

    def test_handler_s3_download_failure_updates_db_status_to_failed_and_raises(
        self, mocker, mock_s3_event, mock_lambda_context, mock_db_connection
    ):
        """Test S3 download failure updates DB status and raises error."""
        # Arrange
        s3_error = S3InteractionError(
            "Failed to download image",
            error_code="S3_DOWNLOAD_FAILED"
        )
        
        # Mock environment variables
        mocker.patch.dict(os.environ, {
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-password',
            'DB_NAME': 'test-db'
        })
        
        # Mock helper functions
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._download_image_from_s3',
            side_effect=s3_error
        )
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._get_db_connection_lambda',
            return_value=mock_db_connection
        )
        mock_update = mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._update_caption_in_db',
            return_value=True
        )
        
        # Act & Assert
        with pytest.raises(S3InteractionError) as exc_info:
            lambda_handler(mock_s3_event, mock_lambda_context)
        
        assert str(exc_info.value) == "Failed to download image"
        assert exc_info.value.error_code == "S3_DOWNLOAD_FAILED"
        
        # Verify DB was updated with failed status
        mock_update.assert_called_once_with(
            mock_db_connection,
            'uploads/test-image.jpg',
            "Failed to download image",
            'failed',
            'test-aws-request-id-123'
        )

    def test_handler_gemini_api_failure_updates_db_status_to_failed_and_raises(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes, mock_db_connection
    ):
        """Test Gemini API failure updates DB status and raises error."""
        # Arrange
        gemini_error = GeminiAPIError(
            "Failed to generate caption",
            error_code="GEMINI_API_ERROR"
        )
        
        # Mock environment variables
        mocker.patch.dict(os.environ, {
            'GEMINI_API_KEY': 'test-api-key',
            'GEMINI_MODEL_NAME': 'gemini-pro-vision',
            'GEMINI_PROMPT': 'Describe this image',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-password',
            'DB_NAME': 'test-db'
        })
        
        # Mock helper functions
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._download_image_from_s3',
            return_value=mock_image_bytes
        )
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._call_gemini_api',
            side_effect=gemini_error
        )
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._get_db_connection_lambda',
            return_value=mock_db_connection
        )
        mock_update = mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._update_caption_in_db',
            return_value=True
        )
        
        # Act & Assert
        with pytest.raises(GeminiAPIError) as exc_info:
            lambda_handler(mock_s3_event, mock_lambda_context)
        
        assert str(exc_info.value) == "Failed to generate caption"
        assert exc_info.value.error_code == "GEMINI_API_ERROR"
        
        # Verify DB was updated with failed status
        mock_update.assert_called_once_with(
            mock_db_connection,
            'uploads/test-image.jpg',
            "Failed to generate caption",
            'failed',
            'test-aws-request-id-123'
        )

    def test_handler_gemini_api_returns_no_caption_updates_db_status_to_failed(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes, mock_db_connection
    ):
        """Test when Gemini API returns no caption."""
        # Arrange
        # Mock environment variables
        mocker.patch.dict(os.environ, {
            'GEMINI_API_KEY': 'test-api-key',
            'GEMINI_MODEL_NAME': 'gemini-pro-vision',
            'GEMINI_PROMPT': 'Describe this image',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-password',
            'DB_NAME': 'test-db'
        })
        
        # Mock helper functions
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._download_image_from_s3',
            return_value=mock_image_bytes
        )
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._call_gemini_api',
            return_value=None
        )
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._get_db_connection_lambda',
            return_value=mock_db_connection
        )
        mock_update = mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._update_caption_in_db',
            return_value=True
        )
        
        # Act
        result = lambda_handler(mock_s3_event, mock_lambda_context)
        
        # Assert
        assert result == {
            'status': 'error',
            's3_key': 'uploads/test-image.jpg',
            'error_type': 'NoCaptionGenerated',
            'message': 'Caption generation failed or content was blocked.'
        }
        
        # Verify DB was updated with failed status
        mock_update.assert_called_once_with(
            mock_db_connection,
            'uploads/test-image.jpg',
            "Caption generation failed or content was blocked.",
            'failed',
            'test-aws-request-id-123'
        )

    def test_handler_gemini_api_key_missing_raises_config_error_and_updates_db(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes, mock_db_connection
    ):
        """Test missing Gemini API key raises config error and updates DB."""
        # Arrange
        # Mock environment variables - intentionally missing GEMINI_API_KEY
        mocker.patch.dict(os.environ, {
            'GEMINI_MODEL_NAME': 'gemini-pro-vision',
            'GEMINI_PROMPT': 'Describe this image',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-password',
            'DB_NAME': 'test-db'
        })
        
        # Mock helper functions
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._download_image_from_s3',
            return_value=mock_image_bytes
        )
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._get_db_connection_lambda',
            return_value=mock_db_connection
        )
        mock_update = mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._update_caption_in_db',
            return_value=True
        )
        
        # Act & Assert
        with pytest.raises(ConfigurationError) as exc_info:
            lambda_handler(mock_s3_event, mock_lambda_context)
        
        assert "GEMINI_API_KEY" in str(exc_info.value)
        
        # Verify DB was updated with failed status
        mock_update.assert_called_once_with(
            mock_db_connection,
            'uploads/test-image.jpg',
            "Missing required environment variable: GEMINI_API_KEY",
            'failed',
            'test-aws-request-id-123'
        )

    def test_handler_db_update_failure_after_gemini_success_raises_db_error(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes, mock_db_connection
    ):
        """Test DB update failure after successful Gemini API call."""
        # Arrange
        db_error = DatabaseError(
            "Failed to update caption in database",
            error_code="DB_UPDATE_FAILED"
        )
        
        # Mock environment variables
        mocker.patch.dict(os.environ, {
            'GEMINI_API_KEY': 'test-api-key',
            'GEMINI_MODEL_NAME': 'gemini-pro-vision',
            'GEMINI_PROMPT': 'Describe this image',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-password',
            'DB_NAME': 'test-db'
        })
        
        # Mock helper functions
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._download_image_from_s3',
            return_value=mock_image_bytes
        )
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._call_gemini_api',
            return_value="A beautiful sunset"
        )
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._get_db_connection_lambda',
            return_value=mock_db_connection
        )
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._update_caption_in_db',
            side_effect=db_error
        )
        
        # Act & Assert
        with pytest.raises(DatabaseError) as exc_info:
            lambda_handler(mock_s3_event, mock_lambda_context)
        
        assert str(exc_info.value) == "Failed to update caption in database"
        assert exc_info.value.error_code == "DB_UPDATE_FAILED"

    def test_handler_db_connection_failure_raises_db_error(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes
    ):
        """Test DB connection failure."""
        # Arrange
        db_error = DatabaseError(
            "Failed to connect to database",
            error_code="DB_CONNECTION_FAILED"
        )
        
        # Mock environment variables
        mocker.patch.dict(os.environ, {
            'GEMINI_API_KEY': 'test-api-key',
            'GEMINI_MODEL_NAME': 'gemini-pro-vision',
            'GEMINI_PROMPT': 'Describe this image',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-password',
            'DB_NAME': 'test-db'
        })
        
        # Mock helper functions
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._download_image_from_s3',
            return_value=mock_image_bytes
        )
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._call_gemini_api',
            return_value="A beautiful sunset"
        )
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._get_db_connection_lambda',
            side_effect=db_error
        )
        
        # Act & Assert
        with pytest.raises(DatabaseError) as exc_info:
            lambda_handler(mock_s3_event, mock_lambda_context)
        
        assert str(exc_info.value) == "Failed to connect to database"
        assert exc_info.value.error_code == "DB_CONNECTION_FAILED"

    def test_handler_invalid_s3_event_structure_logs_error_and_raises_invalid_input_error(
        self, mocker, mock_lambda_context
    ):
        """Test handling of invalid S3 event structure."""
        # Arrange
        invalid_event = {"Records": []}  # Missing required fields
        
        # Act & Assert
        with pytest.raises(InvalidInputError) as exc_info:
            lambda_handler(invalid_event, mock_lambda_context)
        
        assert "Invalid S3 event structure" in str(exc_info.value)

    def test_handler_unexpected_exception_attempts_db_update_and_raises_comp5349a2error(
        self, mocker, mock_s3_event, mock_lambda_context, mock_image_bytes, mock_db_connection
    ):
        """Test handling of unexpected exceptions."""
        # Arrange
        unexpected_error = Exception("Unexpected error")
        
        # Mock environment variables
        mocker.patch.dict(os.environ, {
            'GEMINI_API_KEY': 'test-api-key',
            'GEMINI_MODEL_NAME': 'gemini-pro-vision',
            'GEMINI_PROMPT': 'Describe this image',
            'DB_HOST': 'test-host',
            'DB_USER': 'test-user',
            'DB_PASSWORD': 'test-password',
            'DB_NAME': 'test-db'
        })
        
        # Mock helper functions
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._download_image_from_s3',
            side_effect=unexpected_error
        )
        mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._get_db_connection_lambda',
            return_value=mock_db_connection
        )
        mock_update = mocker.patch(
            'lambda_functions.annotation_lambda.lambda_function._update_caption_in_db',
            return_value=True
        )
        
        # Act & Assert
        with pytest.raises(COMP5349A2Error) as exc_info:
            lambda_handler(mock_s3_event, mock_lambda_context)
        
        assert "Unexpected error" in str(exc_info.value)
        
        # Verify DB was updated with failed status
        mock_update.assert_called_once_with(
            mock_db_connection,
            'uploads/test-image.jpg',
            "Unexpected error occurred during processing",
            'failed',
            'test-aws-request-id-123'
        )

# --- Test Helper Functions ---
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

class TestCallGeminiAPI:
    def test_call_gemini_success(self, mocker):
        """Test successful caption generation using Gemini API."""
        # Arrange
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "A beautiful sunset over mountains"
        mock_model.generate_content.return_value = mock_response
        
        mocker.patch.dict(os.environ, {
            'GEMINI_API_KEY': 'test-api-key',
            'GEMINI_MODEL_NAME': 'gemini-pro-vision',
            'GEMINI_PROMPT': 'Describe this image'
        })
        mocker.patch('google.generativeai.GenerativeModel', return_value=mock_model)
        
        # Act
        result = _call_gemini_api(
            b"mock image content",
            'test-request-id'
        )
        
        # Assert
        assert result == "A beautiful sunset over mountains"
        mock_model.generate_content.assert_called_once()

    def test_call_gemini_api_key_missing_raises_configuration_error(self, mocker):
        """Test missing API key raises ConfigurationError."""
        # Arrange
        mocker.patch.dict(os.environ, {
            'GEMINI_MODEL_NAME': 'gemini-pro-vision',
            'GEMINI_PROMPT': 'Describe this image'
        }, clear=True)
        
        # Act & Assert
        with pytest.raises(ConfigurationError) as exc_info:
            _call_gemini_api(
                b"mock image content",
                'test-request-id'
            )
        
        assert "GEMINI_API_KEY" in str(exc_info.value)

    def test_call_gemini_content_blocked_returns_none(self, mocker):
        """Test when Gemini API blocks content."""
        # Arrange
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("Content blocked")
        
        mocker.patch.dict(os.environ, {
            'GEMINI_API_KEY': 'test-api-key',
            'GEMINI_MODEL_NAME': 'gemini-pro-vision',
            'GEMINI_PROMPT': 'Describe this image'
        })
        mocker.patch('google.generativeai.GenerativeModel', return_value=mock_model)
        
        # Act
        result = _call_gemini_api(
            b"mock image content",
            'test-request-id'
        )
        
        # Assert
        assert result is None

    def test_call_gemini_api_sdk_failure_raises_gemini_api_error(self, mocker):
        """Test Gemini SDK failure raises GeminiAPIError."""
        # Arrange
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("API error")
        
        mocker.patch.dict(os.environ, {
            'GEMINI_API_KEY': 'test-api-key',
            'GEMINI_MODEL_NAME': 'gemini-pro-vision',
            'GEMINI_PROMPT': 'Describe this image'
        })
        mocker.patch('google.generativeai.GenerativeModel', return_value=mock_model)
        
        # Act & Assert
        with pytest.raises(GeminiAPIError) as exc_info:
            _call_gemini_api(
                b"mock image content",
                'test-request-id'
            )
        
        assert "Failed to generate caption" in str(exc_info.value)
        assert exc_info.value.error_code == "GEMINI_API_ERROR"

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
        
        assert "Missing required environment variables" in str(exc_info.value)

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

class TestUpdateCaptionInDB:
    def test_update_caption_success(self, mocker, mock_db_connection):
        """Test successful caption update in database."""
        # Arrange
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1  # 设置 rowcount 为整数
        mock_db_connection.cursor.return_value = mock_cursor
        
        # Act
        result = _update_caption_in_db(
            mock_db_connection,
            'test-image.jpg',
            'A beautiful sunset',
            'completed',
            'test-request-id'
        )
        
        # Assert
        assert result is True
        mock_cursor.execute.assert_called_once()
        mock_db_connection.commit.assert_called_once()

    def test_update_caption_db_error_raises_db_error(self, mocker, mock_db_connection):
        """Test database error during update raises DatabaseError."""
        # Arrange
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 0  # 设置 rowcount 为整数
        mock_cursor.execute.side_effect = mysql.connector.Error("Update failed")
        mock_db_connection.cursor.return_value = mock_cursor
        
        # Act & Assert
        with pytest.raises(DatabaseError) as exc_info:
            _update_caption_in_db(
                mock_db_connection,
                'test-image.jpg',
                'A beautiful sunset',
                'completed',
                'test-request-id'
            )
        
        assert "Failed to update caption in database" in str(exc_info.value)
        assert exc_info.value.error_code == "DB_UPDATE_FAILED"

    def test_update_caption_s3_upload_failure_raises_db_error(self, mocker, mock_db_connection):
        """Test S3 upload failure during update raises DatabaseError."""
        # Arrange
        s3_error = S3InteractionError(
            "Failed to upload image",
            error_code="S3_UPLOAD_FAILED"
        )
        
        # Act & Assert
        with pytest.raises(S3InteractionError) as exc_info:
            _update_caption_in_db(
                mock_db_connection,
                'test-image.jpg',
                'A beautiful sunset',
                'completed',
                'test-request-id'
            )
        
        assert str(exc_info.value) == "Failed to upload image"
        assert exc_info.value.error_code == "S3_UPLOAD_FAILED"

    def test_update_caption_db_connection_failure_raises_db_error(self, mocker, mock_db_connection):
        """Test database connection failure during update raises DatabaseError."""
        # Arrange
        db_error = DatabaseError(
            "Failed to connect to database",
            error_code="DB_CONNECTION_FAILED"
        )
        
        # Act & Assert
        with pytest.raises(DatabaseError) as exc_info:
            _update_caption_in_db(
                mock_db_connection,
                'test-image.jpg',
                'A beautiful sunset',
                'completed',
                'test-request-id'
            )
        
        assert str(exc_info.value) == "Failed to connect to database"
        assert exc_info.value.error_code == "DB_CONNECTION_FAILED"

    def test_update_caption_db_update_failure_raises_db_error(self, mocker, mock_db_connection):
        """Test database update failure during update raises DatabaseError."""
        # Arrange
        db_error = DatabaseError(
            "Failed to update database",
            error_code="DB_UPDATE_FAILED"
        )
        
        # Act & Assert
        with pytest.raises(DatabaseError) as exc_info:
            _update_caption_in_db(
                mock_db_connection,
                'test-image.jpg',
                'A beautiful sunset',
                'completed',
                'test-request-id'
            )
        
        assert str(exc_info.value) == "Failed to update database"
        assert exc_info.value.error_code == "DB_UPDATE_FAILED" 