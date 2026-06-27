from typing import Optional, Any

from pydantic import BaseModel, EmailStr, field_validator

from api.schema.internal.auth import AccessTokenPayload, ReturnTokens


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def lower_email(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.lower()
        return value


class LoginResponse(BaseModel):
    tokens: ReturnTokens


class RegisterRequest(BaseModel):
    username: str
    grade: int
    email: EmailStr
    password: str

    @field_validator("username", "email", mode="before")
    @classmethod
    def lower_username_and_email(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.lower()
        return value


class RegisterResponse(BaseModel):
    tokens: ReturnTokens


class ValidateResponse(BaseModel):
    active: bool
    payload: AccessTokenPayload


class RefreshRequest(BaseModel):
    old_refresh_token: Optional[str]


class RefreshResponse(BaseModel):
    tokens: ReturnTokens

class VerifyEmailResponse(BaseModel):
    success: bool

class ResetForgottenPasswordRequest(BaseModel):
    new_password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class ChangePasswordResponse(BaseModel):
    success: bool

class ResetForgottenPasswordResponse(BaseModel):
    success: bool

class LogoutResponse(BaseModel):
    success: bool


class DeleteResponse(BaseModel):
    success: bool
