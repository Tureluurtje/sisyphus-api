from uuid import UUID
from pydantic import BaseModel, EmailStr

class EmailData(BaseModel):
    to: EmailStr
    subject: str
    message: str

class ReturnTokens(BaseModel):
    refresh_token: str
    access_token: str
    csrf_token: str

class IssuedRefreshToken(BaseModel):
    token: str
    id: UUID


class AccessTokenPayload(BaseModel):
    sub: UUID
    exp: int
    jti: UUID

