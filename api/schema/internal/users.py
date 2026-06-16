from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class Claims(BaseModel):
    sub: str
    exp: int


class UserProfileDetail(BaseModel):
    user_id: UUID
    username: str
    email: str
    grade: int
    total_words_learned: int
    streak: int
    created_at: datetime
    updated_at: datetime
