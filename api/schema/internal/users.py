from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class Claims(BaseModel):
    sub: str
    exp: int


class UserProfileDetail(BaseModel):
    user_id: UUID
    username: str
    grade: int
    email: str
    created_at: datetime
    updated_at: datetime
