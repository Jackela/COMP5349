# utils package for web_app 
# Smart import handling
try:
    from .custom_exceptions import (
        COMP5349A2Error,
        S3InteractionError,
        DatabaseError,
        GeminiAPIError,
        ImageProcessingError,
        InvalidInputError,
        ConfigurationError
    )
except ImportError:
    from utils.custom_exceptions import (
        COMP5349A2Error,
        S3InteractionError,
        DatabaseError,
        GeminiAPIError,
        ImageProcessingError,
        InvalidInputError,
        ConfigurationError
    )
# ... other utils imports ... 