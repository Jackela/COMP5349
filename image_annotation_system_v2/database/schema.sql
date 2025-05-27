-- MySQL-compatible schema for the Image Annotation System
-- This schema unifies the database structure expectations from web_app/utils/db_utils.py
-- and the project requirements for storing image metadata, annotations, and processing status.

CREATE TABLE IF NOT EXISTS images (
    id INT AUTO_INCREMENT PRIMARY KEY,                      -- Auto-incrementing primary key
    filename VARCHAR(255) NOT NULL,                         -- Original uploaded filename
    s3_key_original VARCHAR(1024) NOT NULL UNIQUE,          -- S3 key for original image
    s3_key_thumbnail VARCHAR(1024) UNIQUE,                  -- S3 key for thumbnail (nullable)
    annotation TEXT,                                        -- AI-generated image annotation/description (nullable)
    annotation_status VARCHAR(50) DEFAULT 'pending',        -- Status of annotation task (pending, success, error)
    thumbnail_status VARCHAR(50) DEFAULT 'pending',         -- Status of thumbnail task (pending, success, error)
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,          -- Upload timestamp
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP -- Last update timestamp
);

-- Optional indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_images_annotation_status ON images(annotation_status);
CREATE INDEX IF NOT EXISTS idx_images_thumbnail_status ON images(thumbnail_status);
CREATE INDEX IF NOT EXISTS idx_images_uploaded_at ON images(uploaded_at); 