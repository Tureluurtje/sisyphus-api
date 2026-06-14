from typing import Optional

from pydantic import BaseModel, EmailStr

from api.schema.internal.auth import AccessTokenPayload, ReturnTokens


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    tokens: ReturnTokens


class RegisterRequest(BaseModel):
    username: str
    grade: int
    email: EmailStr
    password: str


class RegisterResponse(BaseModel):
    tokens: ReturnTokens


class ValidateResponse(BaseModel):
    active: bool
    payload: AccessTokenPayload


class RefreshRequest(BaseModel):
    old_refresh_token: Optional[str]

class RefreshResponse(BaseModel):
    tokens: ReturnTokens


class LogoutResponse(BaseModel):
    success: bool
