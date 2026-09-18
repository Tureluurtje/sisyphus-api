from uuid import UUID

from sqlalchemy.orm import Session as DbSession


from api.models.auth import User
from api.models.words import Cards
from api.schema.http.users import UpdateUserSettings
from api.schema.internal.errors import NotImplementedYetError, UserNotFoundError
from api.schema.internal.users import UserProfileDetail
from api.services.auth.accounts import get_user_review_streak


def get_user_profile(user_id: UUID, db: DbSession) -> UserProfileDetail:
    user = db.get(User, user_id)
    if not user:
        raise UserNotFoundError()
    count_words_learned: int = (
        db.query(Cards).where(Cards.user_id == user.id).count()
    )
    streak = get_user_review_streak(user_id=user.id, db=db)

    return UserProfileDetail(
        user_id=user.id,
        username=user.username,
        email=user.email,
        grade=user.grade,
        total_words_learned=count_words_learned,
        streak=streak,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )

def update_user_settings(
    user_id: UUID,
    settings: UpdateUserSettings,
    db: DbSession,
) -> UserProfileDetail:
    user = db.get(User, user_id)

    if user is None:
        raise UserNotFoundError("User not found")

    if settings.grade is not None:
        user.grade = settings.grade

    if settings.email is not None:
        raise NotImplementedYetError()

    db.flush()

    count_words_learned: int = (
        db.query(Cards).where(Cards.user_id == user.id).count()
    )
    streak = get_user_review_streak(user_id=user.id, db=db)

    return UserProfileDetail(
        user_id=user.id,
        username=user.username,
        email=user.email,
        grade=user.grade,
        total_words_learned=count_words_learned,
        streak=streak,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
