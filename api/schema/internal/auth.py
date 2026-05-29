from uuid import UUID
from pydantic import BaseModel


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
