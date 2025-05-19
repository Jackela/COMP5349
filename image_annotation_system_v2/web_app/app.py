# Main Flask application file (routes, app logic) 
import os
import uuid
import logging
from flask import Flask, request, redirect, url_for, render_template, flash, g
from werkzeug.utils import secure_filename
from .utils import s3_utils, db_utils
from .utils.custom_exceptions import (
    COMP5349A2Error,
    S3InteractionError,
    DatabaseError,
    InvalidInputError,
    ConfigurationError,
    GeminiAPIError,
    ImageProcessingError
)
import datetime

# Flask app initialization
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'a_very_secret_dev_key_for_development_only')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB
app.config['S3_IMAGE_BUCKET'] = os.environ.get('S3_IMAGE_BUCKET')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Logging configuration
log_level_str = os.environ.get('LOG_LEVEL', 'INFO').upper()
log_level = getattr(logging, log_level_str, logging.INFO)
if not app.logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s [ReqID: %(request_id)s]')
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)
app.logger.setLevel(log_level)

# Database connection management
@app.before_request
def before_request_tasks():
    """
    Before each request, generate a unique request_id and attempt to establish a DB connection.
    Store both in flask.g for use throughout the request lifecycle.
    """
    g.request_id = str(uuid.uuid4().hex)
    try:
        g.db_conn = db_utils.get_db_connection()
    except ConfigurationError as e:
        app.logger.error(f"Configuration error preventing DB connection: {e.message}", extra={'request_id': g.request_id, 'error_code': getattr(e, 'error_code', None)})
        g.db_conn = None
    except DatabaseError as e:
        app.logger.error(f"Database connection failed in before_request: {e.message}", extra={'request_id': g.request_id, 'error_code': getattr(e, 'error_code', None)})
        g.db_conn = None

@app.teardown_appcontext
def teardown_db(exception=None):
    """
    After each request, close the DB connection if it exists and log any errors.
    """
    db_conn = g.pop('db_conn', None)
    request_id = getattr(g, 'request_id', 'N/A')
    if db_conn is not None:
        try:
            db_conn.close()
        except Exception as e:
            app.logger.error(f"Error closing DB connection: {str(e)}", extra={'request_id': request_id})
    if exception:
        app.logger.error(f"Unhandled exception in request context: {exception}", exc_info=True, extra={'request_id': request_id})

# Global error handlers
@app.errorhandler(DatabaseError)
def handle_database_error(error):
    request_id = getattr(g, 'request_id', 'N/A')
    app.logger.error(f"DatabaseError caught by errorhandler: {error.message}", exc_info=True, extra={'request_id': request_id, 'error_code': getattr(error, 'error_code', None)})
    flash(f"A database error occurred: {error.message}. Please try again later.", 'danger')
    return render_template('error.html', error_message="A critical database error occurred.", error_code=500, request_id=request_id), 500

@app.errorhandler(S3InteractionError)
def handle_s3_error(error):
    request_id = getattr(g, 'request_id', 'N/A')
    app.logger.error(f"S3InteractionError caught by errorhandler: {error.message}", exc_info=True, extra={'request_id': request_id, 'error_code': getattr(error, 'error_code', None)})
    flash(f"An S3 interaction error occurred: {error.message}. Please try again later.", 'danger')
    return render_template('error.html', error_message="A critical S3 error occurred.", error_code=500, request_id=request_id), 500

@app.errorhandler(InvalidInputError)
def handle_invalid_input_error(error):
    request_id = getattr(g, 'request_id', 'N/A')
    app.logger.warning(f"InvalidInputError caught: {error.message}", exc_info=True, extra={'request_id': request_id, 'error_code': getattr(error, 'error_code', None)})
    flash(f"Invalid input: {error.message}", 'warning')
    return redirect(request.referrer or url_for('index_get'))

@app.errorhandler(ConfigurationError)
def handle_config_error(error):
    request_id = getattr(g, 'request_id', 'N/A')
    app.logger.error(f"ConfigurationError caught by errorhandler: {error.message}", exc_info=True, extra={'request_id': request_id, 'error_code': getattr(error, 'error_code', None)})
    flash(f"A configuration error occurred: {error.message}. Please contact the administrator.", 'danger')
    return render_template('error.html', error_message="A configuration error occurred.", error_code=500, request_id=request_id), 500

@app.errorhandler(404)
def page_not_found(error):
    request_id = getattr(g, 'request_id', 'N/A')
    app.logger.info(f"404 Not Found: {request.path}", extra={'request_id': request_id})
    return render_template('error.html', error_message="Page Not Found. The requested URL was not found on the server.", error_code=404, request_id=request_id), 404

@app.errorhandler(413)
def payload_too_large(error):
    request_id = getattr(g, 'request_id', 'N/A')
    app.logger.warning(f"413 Payload Too Large: {request.path}", extra={'request_id': request_id})
    flash("The uploaded file is too large. Maximum size is 16MB.", 'danger')
    return redirect(request.referrer or url_for('index_get'))

@app.errorhandler(500)
def internal_server_error(error):
    request_id = getattr(g, 'request_id', 'N/A')
    app.logger.error(f"Internal Server Error: {error}", exc_info=True, extra={'request_id': request_id})
    original_message = "An unexpected internal server error occurred."
    if hasattr(error, 'original_exception') and isinstance(error.original_exception, COMP5349A2Error):
        original_message = error.original_exception.message
    elif isinstance(error, COMP5349A2Error):
        original_message = error.message
    flash(f"An internal server error occurred: {original_message}. Please try again later.", 'danger')
    return render_template('error.html', error_message=original_message, error_code=500, request_id=request_id), 500

# Helper functions
def allowed_file(filename: str) -> bool:
    """
    Checks if the filename has an allowed extension.
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_mime_type(filename: str) -> str:
    """
    Determines a simple MIME type based on file extension.
    """
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in ['jpg', 'jpeg']:
        return 'image/jpeg'
    if ext == 'png':
        return 'image/png'
    if ext == 'gif':
        return 'image/gif'
    return 'application/octet-stream'

# Routes
@app.route('/', methods=['GET'])
def index_get():
    """
    Displays the main upload form page.
    """
    request_id = getattr(g, 'request_id', 'N/A')
    app.logger.info("GET / - Displaying upload form.", extra={'request_id': request_id})
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_post():
    """
    Handles image upload, S3 storage, and initial DB metadata save.
    """
    request_id = getattr(g, 'request_id', 'N/A')
    if g.db_conn is None:
        flash("Database connection error.", 'danger')
        return render_template('index.html'), 500
    if 'file' not in request.files:
        flash("No file part in the request.", 'danger')
        return render_template('index.html'), 400
    file = request.files['file']
    if file.filename == '':
        flash("No selected file.", 'danger')
        return render_template('index.html'), 400
    if not allowed_file(file.filename):
        flash("Invalid file type. Allowed types: png, jpg, jpeg, gif.", 'danger')
        return render_template('index.html'), 400
    if request.content_length > app.config['MAX_CONTENT_LENGTH']:
        flash("File too large. Maximum size is 16MB.", 'danger')
        return render_template('index.html'), 400
    filename = secure_filename(file.filename)
    s3_key = f"{uuid.uuid4().hex}.{filename.rsplit('.', 1)[1].lower()}"
    app.logger.info(f"Generated s3_key: {s3_key} for file: {filename}", extra={'request_id': request_id})
    content_type = get_mime_type(filename)
    try:
        s3_utils.upload_file_to_s3(file, app.config['S3_IMAGE_BUCKET'], s3_key, content_type, request_id=request_id)
        db_utils.save_initial_image_meta(g.db_conn, s3_key, request_id=request_id)
        flash(f"Image '{filename}' uploaded successfully and is being processed.", 'success')
        return redirect(url_for('gallery_get'))
    except (S3InteractionError, DatabaseError, InvalidInputError, ConfigurationError) as e:
        app.logger.error(f"Upload failed for {filename}: {e.message}", exc_info=True, extra={'request_id': request_id, 'error_code': getattr(e, 'error_code', None)})
        flash(f"Upload failed: {e.message}", 'danger')
        return render_template('index.html'), 500

@app.route('/gallery', methods=['GET'])
def gallery_get():
    """
    Displays the image gallery page with all uploaded images and their metadata.
    """
    request_id = getattr(g, 'request_id', 'N/A')
    if g.db_conn is None:
        flash("Database connection error.", 'danger')
        return render_template('gallery.html', images=[], error_message="Database connection error."), 500
    try:
        image_records = db_utils.get_all_image_data_for_gallery(g.db_conn, request_id=request_id)
        processed_images = []
        for record in image_records:
            img_data = dict(record)
            if isinstance(img_data['uploaded_at'], str):
                img_data['uploaded_at'] = datetime.datetime.fromisoformat(img_data['uploaded_at'].replace('Z', '+00:00'))
            img_data['original_image_url'] = None
            img_data['thumbnail_image_url'] = None
            # Generate presigned URLs, handle failures gracefully
            try:
                if record.get('original_s3_key'):
                    img_data['original_image_url'] = s3_utils.generate_presigned_url(
                        app.config['S3_IMAGE_BUCKET'],
                        record['original_s3_key'],
                        request_id=request_id
                    )
            except S3InteractionError as s3_e_presign:
                app.logger.error(f"Failed to generate presigned URL for S3 key {record.get('original_s3_key')}: {s3_e_presign.message}", extra={'request_id': request_id})
            try:
                if record.get('thumbnail_s3_key') and record.get('thumbnail_status') == 'completed':
                    img_data['thumbnail_image_url'] = s3_utils.generate_presigned_url(
                        app.config['S3_IMAGE_BUCKET'],
                        record['thumbnail_s3_key'],
                        request_id=request_id
                    )
            except S3InteractionError as s3_e_presign:
                app.logger.error(f"Failed to generate presigned URL for S3 key {record.get('thumbnail_s3_key')}: {s3_e_presign.message}", extra={'request_id': request_id})
            processed_images.append(img_data)
        app.logger.info(f"Successfully prepared {len(processed_images)} images for gallery display.", extra={'request_id': request_id})
        return render_template('gallery.html', images=processed_images)
    except DatabaseError as e:
        app.logger.error(f"Failed to load gallery: {e.message}", exc_info=True, extra={'request_id': request_id, 'error_code': getattr(e, 'error_code', None)})
        flash(f"Could not load gallery: {e.message}", 'danger')
        return render_template('gallery.html', images=[], error_message=str(e.message)), 500

@app.route('/health', methods=['GET'])
def health_get():
    """
    Health check endpoint for ALB. Returns 200 if healthy, 503 if DB unavailable.
    """
    request_id = getattr(g, 'request_id', 'N/A')
    try:
        if g.db_conn is None:
            raise DatabaseError("Database connection unavailable.")
        g.db_conn.ping(reconnect=True, attempts=1, delay=0)
        app.logger.info("GET /health - Health check OK.", extra={'request_id': request_id})
        return "OK", 200
    except DatabaseError as e:
        app.logger.error(f"Health check failed: DB error - {e.message}", extra={'request_id': request_id})
        return "Service Unavailable - DB Error", 503
    except Exception as e:
        app.logger.error(f"Health check failed: Unexpected error - {str(e)}", exc_info=True, extra={'request_id': request_id})
        return "Service Unavailable - Internal Error", 503 