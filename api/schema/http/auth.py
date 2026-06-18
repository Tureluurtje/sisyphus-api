from pydantic import BaseModel, EmailStr

from api.schema.internal.auth import AccessTokenPayload, ReturnTokens


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    tokens: ReturnTokens


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterResponse(BaseModel):
    tokens: ReturnTokens


class ValidateResponse(BaseModel):
    active: bool
    payload: AccessTokenPayload


class RefreshResponse(BaseModel):
    tokens: ReturnTokens

class VerifyResponse(BaseModel):
    success: bool

class LogoutResponse(BaseModel):
    success: bool
