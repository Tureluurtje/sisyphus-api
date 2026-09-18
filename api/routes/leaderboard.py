from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as DbSession
from api.database import get_db_session_dependency
from api.services.auth.dependencies import get_user_id, typed_limit
from api.services.leaderboard_service import get_full_leaderboard

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("/")
@typed_limit("30/minute")
def get_leaderboard(
    request: Request,
    user_id: UUID = Depends(get_user_id),
    db: DbSession = Depends(get_db_session_dependency),
):
    return get_full_leaderboard(user_id, db)

@router.get("/me")
@typed_limit("30/minute")
def get_me_leaderboard(
    request: Request,
    user_id: UUID = Depends(get_user_id),
    db: DbSession = Depends(get_db_session_dependency),
): ...
