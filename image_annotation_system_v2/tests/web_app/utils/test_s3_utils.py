# Unit tests for web_app.utils.s3_utils 
import io
import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import NoCredentialsError, ClientError

from web_app.utils.s3_utils import (
    upload_file_to_s3,
    generate_presigned_url
)
from web_app.utils.custom_exceptions import (
    S3InteractionError,
    InvalidInputError
)

# --- Test upload_file_to_s3 ---
class TestUploadFileToS3:
    @pytest.fixture
    def mock_s3_client(self):
        with patch('boto3.client') as mock_client:
            yield mock_client.return_value

    @pytest.fixture
    def test_file_stream(self):
        return io.BytesIO(b"test file content")

    def test_upload_file_success(self, mock_s3_client, test_file_stream):
        # Arrange
        bucket_name = "test-bucket"
        s3_key = "test/file.txt"
        content_type = "text/plain"

        # Act
        result = upload_file_to_s3(test_file_stream, bucket_name, s3_key, content_type)

        # Assert
        assert result is True
        mock_s3_client.upload_fileobj.assert_called_once_with(
            Fileobj=test_file_stream,
            Bucket=bucket_name,
            Key=s3_key,
            ExtraArgs={'ContentType': content_type}
        )

    def test_upload_file_no_credentials(self, mock_s3_client, test_file_stream):
        # Arrange
        bucket_name = "test-bucket"
        s3_key = "test/file.txt"
        content_type = "text/plain"
        mock_s3_client.upload_fileobj.side_effect = NoCredentialsError()

        # Act & Assert
        with pytest.raises(S3InteractionError) as exc_info:
            upload_file_to_s3(test_file_stream, bucket_name, s3_key, content_type)
        assert "AWS credentials not found" in str(exc_info.value)
        assert exc_info.value.error_code == "AWS_NO_CREDENTIALS"

    def test_upload_file_client_error(self, mock_s3_client, test_file_stream):
        # Arrange
        bucket_name = "test-bucket"
        s3_key = "test/file.txt"
        content_type = "text/plain"
        error_response = {
            'Error': {
                'Code': 'AccessDenied',
                'Message': 'Access Denied'
            }
        }
        mock_s3_client.upload_fileobj.side_effect = ClientError(
            error_response=error_response,
            operation_name='UploadFile'
        )

        # Act & Assert
        with pytest.raises(S3InteractionError) as exc_info:
            upload_file_to_s3(test_file_stream, bucket_name, s3_key, content_type)
        assert "S3 upload failed" in str(exc_info.value)
        assert exc_info.value.error_code == "AccessDenied"

    def test_upload_file_unexpected_error(self, mock_s3_client, test_file_stream):
        # Arrange
        bucket_name = "test-bucket"
        s3_key = "test/file.txt"
        content_type = "text/plain"
        mock_s3_client.upload_fileobj.side_effect = Exception("Unexpected error")

        # Act & Assert
        with pytest.raises(S3InteractionError) as exc_info:
            upload_file_to_s3(test_file_stream, bucket_name, s3_key, content_type)
        assert "An unexpected error occurred during S3 upload" in str(exc_info.value)
        assert exc_info.value.error_code == "S3_UNEXPECTED_UPLOAD_ERROR"

# --- Test generate_presigned_url ---
class TestGeneratePresignedUrl:
    @pytest.fixture
    def mock_s3_client(self):
        with patch('boto3.client') as mock_client:
            yield mock_client.return_value

    def test_generate_presigned_url_success(self, mock_s3_client):
        # Arrange
        bucket_name = "test-bucket"
        s3_key = "test/file.txt"
        expiration_seconds = 3600
        expected_url = "https://test-bucket.s3.amazonaws.com/test/file.txt?AWSAccessKeyId=test&Signature=test&Expires=1234567890"
        mock_s3_client.generate_presigned_url.return_value = expected_url

        # Act
        result = generate_presigned_url(bucket_name, s3_key, expiration_seconds)

        # Assert
        assert result == expected_url
        mock_s3_client.generate_presigned_url.assert_called_once_with(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': s3_key},
            ExpiresIn=expiration_seconds
        )

    def test_generate_presigned_url_invalid_expiration(self, mock_s3_client):
        # Arrange
        bucket_name = "test-bucket"
        s3_key = "test/file.txt"
        expiration_seconds = 30  # Too short

        # Act & Assert
        with pytest.raises(InvalidInputError) as exc_info:
            generate_presigned_url(bucket_name, s3_key, expiration_seconds)
        assert "Invalid expiration_seconds" in str(exc_info.value)

    def test_generate_presigned_url_no_credentials(self, mock_s3_client):
        # Arrange
        bucket_name = "test-bucket"
        s3_key = "test/file.txt"
        expiration_seconds = 3600
        mock_s3_client.generate_presigned_url.side_effect = NoCredentialsError()

        # Act & Assert
        with pytest.raises(S3InteractionError) as exc_info:
            generate_presigned_url(bucket_name, s3_key, expiration_seconds)
        assert "AWS credentials not found" in str(exc_info.value)
        assert exc_info.value.error_code == "AWS_NO_CREDENTIALS"

    def test_generate_presigned_url_client_error(self, mock_s3_client):
        # Arrange
        bucket_name = "test-bucket"
        s3_key = "test/file.txt"
        expiration_seconds = 3600
        error_response = {
            'Error': {
                'Code': 'NoSuchBucket',
                'Message': 'The specified bucket does not exist'
            }
        }
        mock_s3_client.generate_presigned_url.side_effect = ClientError(
            error_response=error_response,
            operation_name='GeneratePresignedUrl'
        )

        # Act & Assert
        with pytest.raises(S3InteractionError) as exc_info:
            generate_presigned_url(bucket_name, s3_key, expiration_seconds)
        assert "Failed to generate presigned URL" in str(exc_info.value)
        assert exc_info.value.error_code == "NoSuchBucket"

    def test_generate_presigned_url_unexpected_error(self, mock_s3_client):
        # Arrange
        bucket_name = "test-bucket"
        s3_key = "test/file.txt"
        expiration_seconds = 3600
        mock_s3_client.generate_presigned_url.side_effect = Exception("Unexpected error")

        # Act & Assert
        with pytest.raises(S3InteractionError) as exc_info:
            generate_presigned_url(bucket_name, s3_key, expiration_seconds)
        assert "An unexpected error occurred during presigned URL generation" in str(exc_info.value)
        assert exc_info.value.error_code == "S3_UNEXPECTED_PRESIGNED_URL_ERROR" 