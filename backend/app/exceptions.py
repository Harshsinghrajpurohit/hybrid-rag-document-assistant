"""
Custom exception classes for API error handling.

Design principles:
1. All exceptions include request_id for logging correlation
2. Error responses are structured and user-friendly
3. No stack traces exposed to clients
4. Consistent with ErrorResponse model
"""

from typing import Optional
import uuid


class APIException(Exception):
    """
    Base class for all API exceptions.

    Attributes:
        error_type: Machine-readable error type (e.g., "FILE_TOO_LARGE")
        detail: Human-readable error message
        status_code: HTTP status code
        request_id: UUID for logging correlation
    """

    def __init__(
        self,
        error_type: str,
        detail: str,
        status_code: int,
        request_id: Optional[str] = None
    ):
        self.error_type = error_type
        self.detail = detail
        self.status_code = status_code
        self.request_id = request_id or str(uuid.uuid4())
        super().__init__(detail)


class FileTooLargeError(APIException):
    """Raised when uploaded file exceeds size limit (50 MB)."""

    def __init__(self, file_size: int, request_id: Optional[str] = None):
        detail = f"File exceeds 50 MB limit (provided: {file_size} bytes)"
        super().__init__(
            error_type="FILE_TOO_LARGE",
            detail=detail,
            status_code=413,
            request_id=request_id or str(uuid.uuid4())
        )


class InvalidMimeTypeError(APIException):
    """Raised when file is not a PDF."""

    def __init__(self, request_id: Optional[str] = None):
        detail = "File is not a PDF format"
        super().__init__(
            error_type="INVALID_MIME_TYPE",
            detail=detail,
            status_code=400,
            request_id=request_id or str(uuid.uuid4())
        )


class PdfCorruptedError(APIException):
    """Raised when PDF parsing fails."""

    def __init__(self, request_id: Optional[str] = None):
        detail = "PDF file is corrupted or unreadable"
        super().__init__(
            error_type="PDF_CORRUPTED",
            detail=detail,
            status_code=422,
            request_id=request_id or str(uuid.uuid4())
        )


class DocumentNotFoundError(APIException):
    """Raised when document UUID doesn't exist."""

    def __init__(self, request_id: Optional[str] = None):
        detail = "Document not found"
        super().__init__(
            error_type="DOCUMENT_NOT_FOUND",
            detail=detail,
            status_code=404,
            request_id=request_id or str(uuid.uuid4())
        )


class OllamaUnavailableError(APIException):
    """Raised when LLM service is unavailable."""

    def __init__(self, request_id: Optional[str] = None):
        detail = "LLM service temporarily unavailable"
        super().__init__(
            error_type="OLLAMA_UNAVAILABLE",
            detail=detail,
            status_code=503,
            request_id=request_id or str(uuid.uuid4())
        )


class DeleteFailedError(APIException):
    """Raised when document deletion encounters an error."""

    def __init__(self, request_id: Optional[str] = None):
        detail = "Document deletion failed"
        super().__init__(
            error_type="DELETE_FAILED",
            detail=detail,
            status_code=500,
            request_id=request_id or str(uuid.uuid4())
        )


class DeletePartialError(APIException):
    """Raised when some but not all deletion steps succeed."""

    def __init__(self, request_id: Optional[str] = None):
        detail = "Document deletion partially succeeded"
        super().__init__(
            error_type="DELETE_PARTIAL",
            detail=detail,
            status_code=500,
            request_id=request_id or str(uuid.uuid4())
        )


class InternalServerError(APIException):
    """Raised for unexpected server errors."""

    def __init__(self, request_id: Optional[str] = None):
        detail = "An unexpected error occurred"
        super().__init__(
            error_type="INTERNAL_SERVER_ERROR",
            detail=detail,
            status_code=500,
            request_id=request_id or str(uuid.uuid4())
        )


class InvalidRequestError(APIException):
    """Raised for invalid request parameters."""

    def __init__(self, request_id: Optional[str] = None):
        detail = "Invalid request parameters"
        super().__init__(
            error_type="INVALID_REQUEST",
            detail=detail,
            status_code=400,
            request_id=request_id or str(uuid.uuid4())
        )