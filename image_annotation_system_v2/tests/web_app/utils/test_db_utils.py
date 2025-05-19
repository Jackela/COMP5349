# Unit tests for web_app.utils.db_utils 

import os
import pytest
from unittest.mock import patch, MagicMock
import mysql.connector
from mysql.connector import errorcode

from web_app.utils.db_utils import (
    get_db_connection,
    save_initial_image_meta,
    get_all_image_data_for_gallery,
    update_caption_in_db,
    update_thumbnail_info_in_db
)
from web_app.utils.custom_exceptions import (
    ConfigurationError,
    DatabaseError,
    InvalidInputError
)

# --- Test get_db_connection ---
class TestGetDbConnection:
    @patch.dict(os.environ, {
        'DB_HOST': 'test-host',
        'DB_USER': 'test-user',
        'DB_PASSWORD': 'test-password',
        'DB_NAME': 'test-db',
        'DB_PORT': '3306'
    })
    @patch('mysql.connector.connect')
    def test_get_db_connection_success(self, mock_connect):
        # Arrange
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        # Act
        result = get_db_connection()

        # Assert
        mock_connect.assert_called_once_with(
            host='test-host',
            user='test-user',
            password='test-password',
            database='test-db',
            port='3306',
            connect_timeout=10
        )
        assert result == mock_conn

    @patch.dict(os.environ, {}, clear=True)
    def test_get_db_connection_missing_env_vars(self):
        # Act & Assert
        with pytest.raises(ConfigurationError) as exc_info:
            get_db_connection()
        assert "Database configuration environment variable(s) missing" in str(exc_info.value)

    @patch.dict(os.environ, {
        'DB_HOST': 'test-host',
        'DB_USER': 'test-user',
        'DB_PASSWORD': 'test-password',
        'DB_NAME': 'test-db'
    })
    @patch('mysql.connector.connect')
    def test_get_db_connection_failure(self, mock_connect):
        # Arrange
        mock_connect.side_effect = mysql.connector.Error("Connection failed")

        # Act & Assert
        with pytest.raises(DatabaseError) as exc_info:
            get_db_connection()
        assert "Failed to connect to database" in str(exc_info.value)

# --- Test save_initial_image_meta ---
class TestSaveInitialImageMeta:
    @pytest.fixture
    def mock_db_conn(self):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.lastrowid = 1
        return conn

    def test_save_initial_image_meta_success(self, mock_db_conn):
        # Arrange
        original_s3_key = "test/image.jpg"

        # Act
        result = save_initial_image_meta(mock_db_conn, original_s3_key)

        # Assert
        assert result == 1
        mock_db_conn.cursor().execute.assert_called_once()
        mock_db_conn.commit.assert_called_once()

    def test_save_initial_image_meta_duplicate(self, mock_db_conn):
        # Arrange
        original_s3_key = "test/image.jpg"
        mock_db_conn.cursor().execute.side_effect = mysql.connector.Error(
            errno=errorcode.ER_DUP_ENTRY,
            msg="Duplicate entry"
        )

        # Act & Assert
        with pytest.raises(DatabaseError) as exc_info:
            save_initial_image_meta(mock_db_conn, original_s3_key)
        assert "Duplicate entry" in str(exc_info.value)
        assert exc_info.value.error_code == "DB_UNIQUE_VIOLATION"

    def test_save_initial_image_meta_db_error(self, mock_db_conn):
        # Arrange
        original_s3_key = "test/image.jpg"
        mock_db_conn.cursor().execute.side_effect = mysql.connector.Error(
            msg="General database error"
        )

        # Act & Assert
        with pytest.raises(DatabaseError) as exc_info:
            save_initial_image_meta(mock_db_conn, original_s3_key)
        assert "Failed to save initial image metadata" in str(exc_info.value)

# --- Test get_all_image_data_for_gallery ---
class TestGetAllImageDataForGallery:
    @pytest.fixture
    def mock_db_conn(self):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        return conn

    def test_get_all_image_data_success(self, mock_db_conn):
        # Arrange
        expected_data = [
            {
                'id': 1,
                'original_s3_key': 'test/image1.jpg',
                'caption': 'Test caption 1',
                'thumbnail_s3_key': 'thumbnails/image1.jpg',
                'caption_status': 'completed',
                'thumbnail_status': 'completed',
                'uploaded_at': '2024-03-20 10:00:00'
            },
            {
                'id': 2,
                'original_s3_key': 'test/image2.jpg',
                'caption': 'Test caption 2',
                'thumbnail_s3_key': 'thumbnails/image2.jpg',
                'caption_status': 'completed',
                'thumbnail_status': 'completed',
                'uploaded_at': '2024-03-20 09:00:00'
            }
        ]
        mock_db_conn.cursor().fetchall.return_value = expected_data

        # Act
        result = get_all_image_data_for_gallery(mock_db_conn)

        # Assert
        assert result == expected_data
        mock_db_conn.cursor().execute.assert_called_once()

    def test_get_all_image_data_empty(self, mock_db_conn):
        # Arrange
        mock_db_conn.cursor().fetchall.return_value = []

        # Act
        result = get_all_image_data_for_gallery(mock_db_conn)

        # Assert
        assert result == []
        mock_db_conn.cursor().execute.assert_called_once()

    def test_get_all_image_data_error(self, mock_db_conn):
        # Arrange
        mock_db_conn.cursor().execute.side_effect = mysql.connector.Error(
            msg="Database error"
        )

        # Act & Assert
        with pytest.raises(DatabaseError) as exc_info:
            get_all_image_data_for_gallery(mock_db_conn)
        assert "Failed to retrieve images for gallery" in str(exc_info.value)

# --- Test update_caption_in_db ---
class TestUpdateCaptionInDb:
    @pytest.fixture
    def mock_db_conn(self):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        return conn

    def test_update_caption_success(self, mock_db_conn):
        # Arrange
        original_s3_key = "test/image.jpg"
        caption_text = "New caption"
        status = "completed"
        mock_db_conn.cursor().rowcount = 1

        # Act
        result = update_caption_in_db(mock_db_conn, original_s3_key, caption_text, status)

        # Assert
        assert result is True
        mock_db_conn.cursor().execute.assert_called_once()
        mock_db_conn.commit.assert_called_once()

    def test_update_caption_invalid_status(self, mock_db_conn):
        # Arrange
        original_s3_key = "test/image.jpg"
        caption_text = "New caption"
        status = "invalid_status"

        # Act & Assert
        with pytest.raises(InvalidInputError) as exc_info:
            update_caption_in_db(mock_db_conn, original_s3_key, caption_text, status)
        assert "Invalid status parameter" in str(exc_info.value)

    def test_update_caption_not_found(self, mock_db_conn):
        # Arrange
        original_s3_key = "test/image.jpg"
        caption_text = "New caption"
        status = "completed"
        mock_db_conn.cursor().rowcount = 0

        # Act
        result = update_caption_in_db(mock_db_conn, original_s3_key, caption_text, status)

        # Assert
        assert result is False
        mock_db_conn.cursor().execute.assert_called_once()
        mock_db_conn.commit.assert_called_once()

    def test_update_caption_db_error(self, mock_db_conn):
        # Arrange
        original_s3_key = "test/image.jpg"
        caption_text = "New caption"
        status = "completed"
        mock_db_conn.cursor().execute.side_effect = mysql.connector.Error(
            msg="Database error"
        )

        # Act & Assert
        with pytest.raises(DatabaseError) as exc_info:
            update_caption_in_db(mock_db_conn, original_s3_key, caption_text, status)
        assert "Failed to update caption" in str(exc_info.value)

# --- Test update_thumbnail_info_in_db ---
class TestUpdateThumbnailInfoInDb:
    @pytest.fixture
    def mock_db_conn(self):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        return conn

    def test_update_thumbnail_success(self, mock_db_conn):
        # Arrange
        original_s3_key = "test/image.jpg"
        thumbnail_s3_key = "thumbnails/image.jpg"
        status = "completed"
        mock_db_conn.cursor().rowcount = 1

        # Act
        result = update_thumbnail_info_in_db(mock_db_conn, original_s3_key, thumbnail_s3_key, status)

        # Assert
        assert result is True
        mock_db_conn.cursor().execute.assert_called_once()
        mock_db_conn.commit.assert_called_once()

    def test_update_thumbnail_invalid_status(self, mock_db_conn):
        # Arrange
        original_s3_key = "test/image.jpg"
        thumbnail_s3_key = "thumbnails/image.jpg"
        status = "invalid_status"

        # Act & Assert
        with pytest.raises(InvalidInputError) as exc_info:
            update_thumbnail_info_in_db(mock_db_conn, original_s3_key, thumbnail_s3_key, status)
        assert "Invalid status parameter" in str(exc_info.value)

    def test_update_thumbnail_not_found(self, mock_db_conn):
        # Arrange
        original_s3_key = "test/image.jpg"
        thumbnail_s3_key = "thumbnails/image.jpg"
        status = "completed"
        mock_db_conn.cursor().rowcount = 0

        # Act
        result = update_thumbnail_info_in_db(mock_db_conn, original_s3_key, thumbnail_s3_key, status)

        # Assert
        assert result is False
        mock_db_conn.cursor().execute.assert_called_once()
        mock_db_conn.commit.assert_called_once()

    def test_update_thumbnail_db_error(self, mock_db_conn):
        # Arrange
        original_s3_key = "test/image.jpg"
        thumbnail_s3_key = "thumbnails/image.jpg"
        status = "completed"
        mock_db_conn.cursor().execute.side_effect = mysql.connector.Error(
            msg="Database error"
        )

        # Act & Assert
        with pytest.raises(DatabaseError) as exc_info:
            update_thumbnail_info_in_db(mock_db_conn, original_s3_key, thumbnail_s3_key, status)
        assert "Failed to update thumbnail info" in str(exc_info.value) 