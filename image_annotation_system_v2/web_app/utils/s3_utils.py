# s3_utils.py - S3 interaction utilities 
import os
import io
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from typing import Optional, Union
# Smart import handling
try:
    from .custom_exceptions import COMP5349A2Error, S3InteractionError, InvalidInputError, ConfigurationError
except ImportError:
    from utils.custom_exceptions import COMP5349A2Error, S3InteractionError, InvalidInputError, ConfigurationError

def upload_file_to_s3(
    file_stream: Union[io.BytesIO, 'werkzeug.datastructures.FileStorage'],
    bucket_name: str,
    s3_key: str,
    content_type: str,
    request_id: Optional[str] = None
) -> bool:
    """
    Uploads a given file stream to a specified S3 bucket and key, setting its content type.

    Args:
        file_stream: A file-like object (e.g., io.BytesIO or werkzeug FileStorage) to upload.
        bucket_name: The name of the S3 bucket to upload to.
        s3_key: The S3 object key under which to store the file.
        content_type: The MIME type to set for the uploaded object.
        request_id: Optional. The request ID for logging correlation.

    Raises:
        S3InteractionError: If AWS credentials are missing, the upload fails, or an unexpected error occurs.

    Returns:
        bool: True if the upload succeeds.
    """
    s3_client = boto3.client('s3')
    try:
        s3_client.upload_fileobj(
            Fileobj=file_stream,
            Bucket=bucket_name,
            Key=s3_key,
            ExtraArgs={'ContentType': content_type}
        )
        return True
    except NoCredentialsError as e:
        raise S3InteractionError(
            message="AWS credentials not found.",
            error_code="AWS_NO_CREDENTIALS",
            original_exception=e
        )
    except ClientError as e:
        error_code_from_s3 = e.response.get('Error', {}).get('Code')
        raise S3InteractionError(
            message=f"S3 upload failed: {e.response.get('Error', {}).get('Message', str(e))}",
            error_code=error_code_from_s3 if error_code_from_s3 else "S3_UPLOAD_FAILED",
            original_exception=e
        )
    except Exception as e:
        raise S3InteractionError(
            message=f"An unexpected error occurred during S3 upload: {str(e)}",
            error_code="S3_UNEXPECTED_UPLOAD_ERROR",
            original_exception=e
        )

def generate_presigned_url(
    bucket_name: str,
    s3_key: str,
    expiration_seconds: int = 3600,
    request_id: Optional[str] = None
) -> str:
    """
    Generates a presigned URL for temporary GET access to an S3 object.

    Args:
        bucket_name: The name of the S3 bucket.
        s3_key: The S3 object key.
        expiration_seconds: The number of seconds the presigned URL is valid for (60-604800).
        request_id: Optional. The request ID for logging correlation.

    Raises:
        InvalidInputError: If expiration_seconds is not between 60 and 604800.
        S3InteractionError: If AWS credentials are missing, the operation fails, or an unexpected error occurs.

    Returns:
        str: The generated presigned URL.
    """
    if not (60 <= expiration_seconds <= 604800):
        raise InvalidInputError(
            message=f"Invalid expiration_seconds: {expiration_seconds}. Must be between 60 and 604800 seconds."
        )
    s3_client = boto3.client('s3')
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': s3_key},
            ExpiresIn=expiration_seconds
        )
        return url
    except NoCredentialsError as e:
        raise S3InteractionError(
            message="AWS credentials not found for generating presigned URL.",
            error_code="AWS_NO_CREDENTIALS",
            original_exception=e
        )
    except ClientError as e:
        error_code_from_s3 = e.response.get('Error', {}).get('Code')
        raise S3InteractionError(
            message=f"Failed to generate presigned URL for s3://{bucket_name}/{s3_key}: {e.response.get('Error', {}).get('Message', str(e))}",
            error_code=error_code_from_s3 if error_code_from_s3 else "S3_PRESIGN_FAILED",
            original_exception=e
        )
    except Exception as e:
        raise S3InteractionError(
            message=f"An unexpected error occurred during presigned URL generation for s3://{bucket_name}/{s3_key}: {str(e)}",
            error_code="S3_UNEXPECTED_PRESIGNED_URL_ERROR",
            original_exception=e
        ) 