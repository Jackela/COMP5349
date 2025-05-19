-- SQL script to create the 'images' table
-- Detailed schema will be defined based on the design document.

CREATE TABLE IF NOT EXISTS images (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    s3_key VARCHAR(1024) NOT NULL UNIQUE,
    thumbnail_s3_key VARCHAR(1024) UNIQUE,
    upload_timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
    tags TEXT[],
    annotations JSONB -- Store annotations as a JSON object or array
);

-- Example: CREATE INDEX idx_tags ON images USING GIN (tags);
-- Example: CREATE INDEX idx_annotations ON images USING GIN (annotations); 