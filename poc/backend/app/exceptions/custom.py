class AppError(Exception):
    """Base application domain exception."""


class NotFoundError(AppError):
    """Raised when a requested entity or file does not exist."""


class ConflictError(AppError):
    """Raised when an operation conflicts with current resource state."""


class ValidationError(AppError):
    """Raised when input violates domain validation rules."""


class UpstreamError(AppError):
    """Raised when an upstream service (NVR, VMS Storage, MQTT) fails."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code
