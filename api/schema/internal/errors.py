from fastapi import status
from pydantic import BaseModel
from typing import Any, Optional


class APIError(BaseModel):
    error: str
    code: str
    detail: Optional[Any] = None


class AppException(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "APP_ERROR"
    message: str = "Application error"

    def __init__(self, message: Optional[str] = None, detail: Any = None):
        if message:
            self.message = message
        self.detail = detail


class BadRequestError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "BAD_REQUEST"
    message = "The request could not be processed"


class InvalidInputError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "INVALID_INPUT"
    message = "One or more fields contain invalid values"


class MissingFieldError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "MISSING_FIELD"
    message = "A required field is missing"


class InvalidFormatError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "INVALID_FORMAT"
    message = "The provided data format is invalid"


class UnauthorizedError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"
    message = "Authentication is required"


class DatabaseConnectionError(AppException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "DATABASE_CONNECTION_ERROR"
    message = "Database connection failed. Please try again later."


class InvalidCredentialsError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "INVALID_CREDENTIALS"
    message = "The provided credentials are incorrect"

class AccountNotVerifiedError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "ACCOUNT_NOT_VERIFIED"
    message = "This account is not yet verified"


class TokenExpiredError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "TOKEN_EXPIRED"
    message = "The authentication token has expired"


class TokenInvalidError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "TOKEN_INVALID"
    message = "The authentication token is invalid"


class TokenMissingError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "TOKEN_MISSING"
    message = "Authentication token is missing"


class RefreshTokenMissingError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "REFRESH_TOKEN_MISSING"
    message = "Refresh token is missing"


class RefreshTokenInvalidError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "REFRESH_TOKEN_INVALID"
    message = "The refresh token is invalid"

class VerificationTokenInvalidError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "VERIFICATION_TOKEN_INVALID"
    message = "The verification token is invalid"


class ForbiddenError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"
    message = "You do not have permission to perform this action"


class InsufficientPermissionsError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    code = "INSUFFICIENT_PERMISSIONS"
    message = "Your account lacks the required permissions"


class AccountDisabledError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    code = "ACCOUNT_DISABLED"
    message = "This account has been disabled"


class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"
    message = "The requested resource was not found"


class UserNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    code = "USER_NOT_FOUND"
    message = "The specified user does not exist"


class ResourceNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    code = "RESOURCE_NOT_FOUND"
    message = "The requested resource does not exist"


class EndpointNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    code = "ENDPOINT_NOT_FOUND"
    message = "The requested endpoint does not exist"


class ConflictError(AppException):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"
    message = "The request conflicts with the current state"


class ResourceAlreadyExistsError(AppException):
    status_code = status.HTTP_409_CONFLICT
    code = "RESOURCE_ALREADY_EXISTS"
    message = "The resource already exists"


class EmailAlreadyRegisteredError(AppException):
    status_code = status.HTTP_409_CONFLICT
    code = "EMAIL_ALREADY_REGISTERED"
    message = "This email address is already registered"


class UsernameTakenError(AppException):
    status_code = status.HTTP_409_CONFLICT
    code = "USERNAME_TAKEN"
    message = "This username is already taken"


class ValidationError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "VALIDATION_ERROR"
    message = "The request validation failed"


class SchemaValidationError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "SCHEMA_VALIDATION_ERROR"
    message = "The request body does not match the required schema"


class RateLimitedError(AppException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMITED"
    message = "Too many requests. Please try again later"


class InternalError(AppException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "INTERNAL_ERROR"
    message = "An unexpected internal error occurred"


class DatabaseError(AppException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "DATABASE_ERROR"
    message = "A database error occurred"


class ServiceUnavailableError(AppException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "SERVICE_UNAVAILABLE"
    message = "The service is temporarily unavailable"


class NotImplementedYetError(AppException):
    status_code = status.HTTP_501_NOT_IMPLEMENTED
    code = "NOT_IMPLEMENTED"
    message = "This service is not (yet) implemented"


class DependencyUnavailableError(AppException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "DEPENDENCY_UNAVAILABLE"
    message = "A required service is unavailable"


class MaintenanceModeError(AppException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "MAINTENANCE_MODE"
    message = "The system is under maintenance"
