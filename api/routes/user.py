from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as DbSession

from api.database import get_db_session_dependency
from api.schema.internal.users import UserProfileDetail
from api.services.auth.accounts import get_user_profile
from api.services.auth.dependencies import get_user_id_skip_csrf, typed_limit

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me")
@typed_limit("60/minute")
def get_current_user(
    request: Request, user_id: UUID = Depends(get_user_id_skip_csrf), db: DbSession = Depends(get_db_session_dependency)
) -> UserProfileDetail:
    return get_user_profile(user_id=user_id, db=db)

