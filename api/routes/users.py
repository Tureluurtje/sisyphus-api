from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as DbSession

from api.database import get_db_session_dependency
from api.schema.http.users import UpdateUserSettings
from api.schema.internal.users import UserProfileDetail
from api.services.auth.dependencies import (
    get_user_id,
    get_user_id_skip_csrf,
    typed_limit,
)
from api.services.users_service import update_user_settings, get_user_profile

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
@typed_limit("60/minute")
def get_current_user(
    request: Request,
    user_id: UUID = Depends(get_user_id_skip_csrf),
    db: DbSession = Depends(get_db_session_dependency),
) -> UserProfileDetail:
    return get_user_profile(user_id=user_id, db=db)


@router.patch("/settings")
@typed_limit("30/minute")
def update_settings(
    request: Request,
    settings: UpdateUserSettings,
    user_id: UUID = Depends(get_user_id),
    db: DbSession = Depends(get_db_session_dependency),
) -> UserProfileDetail:
    updated_user_profile = update_user_settings(
        user_id=user_id, settings=settings, db=db
    )
    db.commit()
    return updated_user_profile
