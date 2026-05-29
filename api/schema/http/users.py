from pydantic import BaseModel, field_validator, Field
from typing import Optional, Any
from datetime import datetime


class UpdateUserProfileRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    date_of_birth: Optional[datetime] = Field(
        None, description="Date in DD-MM-YYYY format"
    )
    location: Optional[str] = None
    website: Optional[str] = None

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def validate_date_of_birth(cls, v: Any):
        if v is None or v == "":
            return None

        if isinstance(v, datetime):
            return v

        if not isinstance(v, str):
            raise ValueError("date_of_birth must be a string in DD-MM-YYYY format")

        try:
            return datetime.strptime(v, "%d-%m-%Y")
        except ValueError:
            raise ValueError(
                "date_of_birth must be in DD-MM-YYYY format (e.g., 04-12-2025)"
            )

    class ConfigDict:
        from_attributes = True
