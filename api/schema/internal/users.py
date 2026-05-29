from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from datetime import datetime


class Claims(BaseModel):
    sub: str
    exp: int


class UserProfileDetail(BaseModel):
    user_id: UUID = Field(validation_alias="id")
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: str
    created_at: datetime
    updated_at: datetime
    hourly_rate: Optional[float] = Field(None, validation_alias="default_hourly_rate")

    model_config = ConfigDict(from_attributes=True)
