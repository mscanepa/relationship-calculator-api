from fastapi import HTTPException, status
from typing import Any, Dict
from app.logger import logger

class APIException(HTTPException):
    """Base exception for API errors."""
    def __init__(
        self,
        status_code: int,
        detail: str,
        error_code: str = None,
        headers: Dict[str, Any] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.error_code = error_code
        logger.error(
            "API Error",
            status_code=status_code,
            detail=detail,
            error_code=error_code
        )

class ValidationError(APIException):
    """Exception for validation errors."""
    def __init__(self, detail: str, error_code: str = "VALIDATION_ERROR"):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
            error_code=error_code
        )

class NotFoundError(APIException):
    """Exception for not found errors."""
    def __init__(self, detail: str, error_code: str = "NOT_FOUND"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            error_code=error_code
        )

class RateLimitError(APIException):
    """Exception for rate limit errors."""
    def __init__(self, detail: str = "Rate limit exceeded"):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            error_code="RATE_LIMIT_EXCEEDED"
        ) 