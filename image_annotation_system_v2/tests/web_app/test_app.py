# Unit tests for web_app.app 
import io
import pytest
from unittest.mock import patch, MagicMock
from werkzeug.datastructures import FileStorage
from web_app.utils.custom_exceptions import (
    S3InteractionError,
    DatabaseError,
    InvalidInputError
)

# --- Test Index Route ---
class TestIndexRoute:
    def test_index_get_returns_200_and_renders_index_template(self, client):
        """Test that GET / returns 200 and renders index template."""
        # Act
        response = client.get('/')
        
        # Assert
        assert response.status_code == 200
        assert b'Upload New Image' in response.data
        assert b'form' in response.data
        assert b'enctype="multipart/form-data"' in response.data

# --- Test Upload Route ---
class TestUploadRoute:
    @pytest.fixture
    def mock_image_file(self):
        """Create a mock image file for testing."""
        return (io.BytesIO(b'test image content'), 'test.jpg')

    def test_upload_post_successful_file_redirects_to_gallery(
        self, client, mock_db_connection, mock_s3_client, mock_image_file
    ):
        """Test successful file upload redirects to gallery."""
        # Arrange
        mock_db_connection.cursor().lastrowid = 1
        
        # Act
        response = client.post(
            '/upload',
            data={'file': mock_image_file},
            content_type='multipart/form-data'
        )
        
        # Assert
        assert response.status_code == 302
        assert response.location == '/gallery'
        
        # Verify S3 upload was called
        mock_s3_client.upload_fileobj.assert_called_once()
        call_args = mock_s3_client.upload_fileobj.call_args[1]
        assert call_args['Bucket'] == 'test-image-bucket'
        assert call_args['Key'].startswith('uploads/')
        assert call_args['ExtraArgs']['ContentType'] == 'image/jpeg'
        
        # Verify DB save was called
        mock_db_connection.cursor().execute.assert_called_once()
        mock_db_connection.commit.assert_called_once()

    def test_upload_post_no_file_part(self, client):
        """Test upload with no file part returns 400."""
        # Act
        response = client.post('/upload')
        
        # Assert
        assert response.status_code == 400
        assert b'No file part' in response.data

    def test_upload_post_empty_filename(self, client):
        """Test upload with empty filename returns 400."""
        # Arrange
        empty_file = (io.BytesIO(b''), '')
        
        # Act
        response = client.post(
            '/upload',
            data={'file': empty_file},
            content_type='multipart/form-data'
        )
        
        # Assert
        assert response.status_code == 400
        assert b'No selected file' in response.data

    def test_upload_post_invalid_file_type(self, client):
        """Test upload with invalid file type returns 400."""
        # Arrange
        invalid_file = (io.BytesIO(b'test content'), 'test.txt')
        
        # Act
        response = client.post(
            '/upload',
            data={'file': invalid_file},
            content_type='multipart/form-data'
        )
        
        # Assert
        assert response.status_code == 400
        assert b'Invalid file type' in response.data

    def test_upload_post_s3_upload_failure(
        self, client, mock_db_connection, mock_s3_client, mock_image_file
    ):
        """Test S3 upload failure returns 500."""
        # Arrange
        mock_s3_client.upload_fileobj.side_effect = S3InteractionError(
            "S3 upload failed",
            error_code="S3_UPLOAD_FAILED"
        )
        
        # Act
        response = client.post(
            '/upload',
            data={'file': mock_image_file},
            content_type='multipart/form-data'
        )
        
        # Assert
        assert response.status_code == 500
        assert b'Failed to upload image' in response.data

    def test_upload_post_db_save_failure(
        self, client, mock_db_connection, mock_s3_client, mock_image_file
    ):
        """Test DB save failure returns 500."""
        # Arrange
        mock_db_connection.cursor().execute.side_effect = DatabaseError(
            "Failed to save image metadata",
            error_code="DB_UPDATE_FAILED"
        )
        
        # Act
        response = client.post(
            '/upload',
            data={'file': mock_image_file},
            content_type='multipart/form-data'
        )
        
        # Assert
        assert response.status_code == 500
        assert b'Failed to save image metadata' in response.data

    def test_upload_post_file_too_large(self, client):
        """Test upload of file exceeding size limit returns 400."""
        # Arrange
        large_file = (io.BytesIO(b'x' * (17 * 1024 * 1024)), 'large.jpg')  # 17MB
        
        # Act
        response = client.post(
            '/upload',
            data={'file': large_file},
            content_type='multipart/form-data'
        )
        
        # Assert
        assert response.status_code == 400
        assert b'File too large' in response.data 

# --- Test Gallery Route ---
class TestGalleryRoute:
    @pytest.fixture
    def mock_image_records(self):
        """Create mock image records for testing."""
        return [
            {
                'id': 1,
                'original_s3_key': 'uploads/test1.jpg',
                'caption': 'A beautiful sunset',
                'thumbnail_s3_key': 'thumbnails/test1.jpg',
                'caption_status': 'completed',
                'thumbnail_status': 'completed',
                'uploaded_at': '2024-03-20 10:00:00'
            },
            {
                'id': 2,
                'original_s3_key': 'uploads/test2.jpg',
                'caption': None,
                'thumbnail_s3_key': None,
                'caption_status': 'pending',
                'thumbnail_status': 'pending',
                'uploaded_at': '2024-03-20 10:01:00'
            },
            {
                'id': 3,
                'original_s3_key': 'uploads/test3.jpg',
                'caption': 'Failed to generate caption',
                'thumbnail_s3_key': None,
                'caption_status': 'failed',
                'thumbnail_status': 'failed',
                'uploaded_at': '2024-03-20 10:02:00'
            }
        ]

    def test_gallery_get_empty_db_shows_no_images_message(
        self, client, mock_db_connection
    ):
        """Test gallery shows appropriate message when no images exist."""
        # Arrange
        mock_db_connection.cursor().fetchall.return_value = []
        
        # Act
        response = client.get('/gallery')
        
        # Assert
        assert response.status_code == 200
        assert b'No images uploaded yet' in response.data
        mock_db_connection.cursor().execute.assert_called_once()

    def test_gallery_get_populates_images_with_presigned_urls_and_statuses(
        self, client, mock_db_connection, mock_s3_client, mock_image_records
    ):
        """Test gallery successfully displays images with presigned URLs."""
        # Arrange
        mock_db_connection.cursor().fetchall.return_value = mock_image_records
        mock_s3_client.generate_presigned_url.side_effect = [
            'http://mock.s3/original1.jpg',  # For first image original
            'http://mock.s3/thumb1.jpg',     # For first image thumbnail
            'http://mock.s3/original2.jpg',  # For second image original
            'http://mock.s3/original3.jpg'   # For third image original
        ]
        
        # Act
        response = client.get('/gallery')
        
        # Assert
        assert response.status_code == 200
        
        # Check if all image data is present
        for record in mock_image_records:
            assert record['original_s3_key'].encode() in response.data
            if record['caption']:
                assert record['caption'].encode() in response.data
            assert record['caption_status'].encode() in response.data
            assert record['thumbnail_status'].encode() in response.data
        
        # Verify S3 presigned URL generation calls
        assert mock_s3_client.generate_presigned_url.call_count == 4
        call_args_list = mock_s3_client.generate_presigned_url.call_args_list
        
        # Verify first image (completed status) gets both original and thumbnail URLs
        assert call_args_list[0][1]['Key'] == 'uploads/test1.jpg'
        assert call_args_list[1][1]['Key'] == 'thumbnails/test1.jpg'
        
        # Verify second image (pending status) gets only original URL
        assert call_args_list[2][1]['Key'] == 'uploads/test2.jpg'
        
        # Verify third image (failed status) gets only original URL
        assert call_args_list[3][1]['Key'] == 'uploads/test3.jpg'

    def test_gallery_get_db_failure_shows_error_message(
        self, client, mock_db_connection
    ):
        """Test gallery handles database errors appropriately."""
        # Arrange
        mock_db_connection.cursor().execute.side_effect = DatabaseError(
            "Failed to connect to database",
            error_code="DB_CONNECTION_FAILED"
        )
        
        # Act
        response = client.get('/gallery')
        
        # Assert
        assert response.status_code == 500
        assert b'A critical database error occurred' in response.data

    def test_gallery_get_s3_presigned_url_failure_for_one_image_still_renders_others(
        self, client, mock_db_connection, mock_s3_client, mock_image_records
    ):
        """Test gallery continues to render when presigned URL generation fails for one image."""
        # Arrange
        mock_db_connection.cursor().fetchall.return_value = mock_image_records
        
        # Configure S3 client to fail for second image
        def mock_generate_presigned_url(**kwargs):
            if kwargs['Key'] == 'uploads/test2.jpg':
                raise S3InteractionError(
                    "Failed to generate presigned URL",
                    error_code="S3_PRESIGN_FAILED"
                )
            return f"http://mock.s3/{kwargs['Key']}"
        
        mock_s3_client.generate_presigned_url.side_effect = mock_generate_presigned_url
        
        # Act
        response = client.get('/gallery')
        
        # Assert
        assert response.status_code == 200
        
        # Verify successful images are still rendered
        assert b'uploads/test1.jpg' in response.data
        assert b'uploads/test3.jpg' in response.data
        
        # Verify failed image is handled gracefully
        assert b'uploads/test2.jpg' in response.data  # Original key should still be in response
        assert b'Processing...' in response.data      # Should show pending status

    def test_gallery_get_handles_pending_and_failed_statuses(
        self, client, mock_db_connection, mock_s3_client, mock_image_records
    ):
        """Test gallery correctly displays different processing statuses."""
        # Arrange
        mock_db_connection.cursor().fetchall.return_value = mock_image_records
        mock_s3_client.generate_presigned_url.return_value = 'http://mock.s3/test.jpg'
        
        # Act
        response = client.get('/gallery')
        
        # Assert
        assert response.status_code == 200
        
        # Check status indicators
        assert b'completed' in response.data
        assert b'pending' in response.data
        assert b'failed' in response.data
        
        # Check specific status messages
        assert b'Processing...' in response.data  # For pending status
        assert b'Caption generation failed' in response.data  # For failed status
        assert b'A beautiful sunset' in response.data  # For completed status

# --- Test Health Route ---
class TestHealthRoute:
    def test_health_check_db_ok_returns_200(self, client, mock_db_connection):
        """Test health check returns 200 when database is healthy."""
        # Arrange
        mock_db_connection.ping.return_value = True
        
        # Act
        response = client.get('/health')
        
        # Assert
        assert response.status_code == 200
        assert response.data == b'OK'
        mock_db_connection.ping.assert_called_once()

    def test_health_check_db_ping_error_returns_503(self, client, mock_db_connection):
        """Test health check returns 503 when database ping fails."""
        # Arrange
        mock_db_connection.ping.side_effect = DatabaseError(
            "Failed to ping database",
            error_code="DB_PING_FAILED"
        )
        
        # Act
        response = client.get('/health')
        
        # Assert
        assert response.status_code == 503
        assert b'Service Unavailable - DB Error' in response.data

    def test_health_check_db_conn_none_returns_503(self, client):
        """Test health check returns 503 when database connection is None."""
        # Arrange
        with patch('web_app.app.g') as mock_g:
            mock_g.db_conn = None
            
            # Act
            response = client.get('/health')
            
            # Assert
            assert response.status_code == 503
            assert b'Service Unavailable - DB Error' in response.data

    def test_health_check_unexpected_exception_returns_503(self, client, mock_db_connection):
        """Test health check returns 503 when unexpected error occurs."""
        # Arrange
        mock_db_connection.ping.side_effect = Exception("Unexpected error")
        
        # Act
        response = client.get('/health')
        
        # Assert
        assert response.status_code == 503
        assert b'Service Unavailable - Internal Error' in response.data 