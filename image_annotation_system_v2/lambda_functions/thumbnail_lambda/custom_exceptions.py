from typing import Optional

class COMP5349A2Error(Exception):
    """Base class for all custom exceptions in the COMP5349 Assignment 2 project."""
    def __init__(self, message: str, error_code: Optional[str] = None, original_exception: Optional[Exception] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.original_exception = original_exception

    def __str__(self) -> str:
        return f"{self.__class__.__name__}: {self.message}" + (f" (Code: {self.error_code})" if self.error_code else "")

class S3InteractionError(COMP5349A2Error):
    """Custom exception for errors during S3 interactions."""
    pass

class DatabaseError(COMP5349A2Error):
    """Custom exception for errors during database operations."""
    pass

class GeminiAPIError(COMP5349A2Error):
    """Custom exception for errors when interacting with the Gemini API."""
    pass

class ImageProcessingError(COMP5349A2Error):
    """Custom exception for errors during image processing (e.g., thumbnail generation)."""
    pass

class InvalidInputError(COMP5349A2Error):
    """Custom exception for invalid user input or function arguments."""
    pass

class ConfigurationError(COMP5349A2Error):
    """Custom exception for project configuration issues (e.g., missing environment variables)."""
    pass 