from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from api.database import get_db_session
from api.models.auth import User, VerificationTokenPurposes
from api.models.words import Cards, Reviews
from api.schema.internal.auth import AuthTokens
from api.schema.internal.errors import (
    AccountNotVerifiedError,
    BadRequestError,
    ConflictError,
    InvalidCredentialsError,
    InvalidInputError,
    UserNotFoundError,
)
from api.schema.internal.users import UserProfileDetail
from api.services.auth.passwords import hash_password, set_password, verify_password
from api.services.auth.tokens import (
    issue_auth_tokens,
    verify_verification_token,
)
from api.services.auth.passwords import validate_password_strength, set_password


def user_is_verified(user_id: UUID, db: DbSession) -> bool:
    user = get_user(user_id, db)
    if not user:
        raise UserNotFoundError()
    return user.verified


def get_user(user_id: UUID, db: DbSession) -> Optional[User]:
    return db.get(User, user_id)


def change_user_password(
    user_id: UUID, old_password: str, new_password: str, db: DbSession
):
    user = db.get(User, user_id)

    if not user:
        raise UserNotFoundError()

    # Check old password
    if not verify_password(password=old_password, hashed_password=user.password):
        raise InvalidCredentialsError()

    # Reset password
    set_password(password=new_password, user_object=user)
    db.flush()


def authenticate_user(email: str, password: str) -> AuthTokens:
    with get_db_session() as db:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            # Don't raise UserNotFoundError so attacker has less information
            raise InvalidCredentialsError()

        password_correct = verify_password(
            password=password, hashed_password=user.password
        )

        if not password_correct:
            raise InvalidCredentialsError()

        if user.verified == False:
            raise AccountNotVerifiedError()

        # User verified successfully: Create tokens
        new_tokens = issue_auth_tokens(user_id=user.id, db=db)
        db.commit()

    return new_tokens


def register_user(username: str, grade: int, email: str, password: str) -> AuthTokens:
    if grade not in (1, 2, 3, 4, 5, 6):
        raise InvalidInputError("grade must be 1, 2, 3, 4, 5, 6")

    validate_password_strength(password=password, email=email)

    with get_db_session() as db:
        try:
            # Hash the password before storing
            hashed_password = hash_password(password=password)

            # Create a new User instance
            new_user = User(
                username=username,
                grade=grade,
                email=email,
                password=hashed_password,
            )

            # Add and commit to the database
            db.add(instance=new_user)
            db.flush()  # Get the generated user ID

            new_tokens = issue_auth_tokens(user_id=new_user.id, db=db)

            # Import lazily to keep the auth package import graph acyclic.
            from api.services.auth.email import send_verification_email

            send_verification_email(user_id=new_user.id, db=db)

            db.commit()
            return new_tokens

        except IntegrityError as e:
            db.rollback()  # if email or username is already in use
            if "username" in str(e.args):
                raise ConflictError(message="duplicate username")
            else:
                raise ConflictError(message="duplicate email")


# TODO: Soft delete account first
def delete_account(user_id: UUID) -> None:
    with get_db_session() as db:
        user_to_delete = db.get(User, user_id)
        if not user_to_delete:
            raise UserNotFoundError()
        db.delete(user_to_delete)
        db.commit()


def get_user_profile(user_id: UUID) -> UserProfileDetail:
    with get_db_session() as db:
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


def get_user_review_streak(user_id: UUID, db: DbSession) -> int:
    """
    Returns current consecutive-day review streak for a user,
    allowing a 1-day grace period.
    """

    rows = (
        db.query(func.date(Reviews.reviewed_at))
        .filter(Reviews.user_id == user_id)
        .distinct()
        .all()
    )

    if not rows:
        return 0

    review_dates = sorted((r[0] for r in rows), reverse=True)

    today = date.today()
    expected = today

    streak = 0
    grace_used = False

    for d in review_dates:

        # exact match → normal streak progression
        if d == expected:
            streak += 1
            expected -= timedelta(days=1)
            continue

        # allow 1-day grace (skip one missing day once)
        if not grace_used and d == expected - timedelta(days=1):
            grace_used = True
            streak += 1
            expected -= timedelta(days=2)  # skip the missed day
            continue

        # anything older breaks the streak
        if d < expected - timedelta(days=1):
            break

    return streak


def verify_email(token: str) -> None:
    with get_db_session() as db:
        verification_token = verify_verification_token(
            token=token,
            purpose=VerificationTokenPurposes.EMAIL_VERIFICATION,
            db=db,
        )

        user = db.get(User, verification_token.user_id)

        if not user:
            raise UserNotFoundError()

        if user.verified:
            raise BadRequestError("User already verified")

        db.delete(verification_token)
        db.commit()


def reset_password(token: str, new_password: str) -> None:
    with get_db_session() as db:
        verification_token = verify_verification_token(
            token=token,
            purpose=VerificationTokenPurposes.PASSWORD_RESET,
            db=db,
        )

        user = get_user(user_id=verification_token.user_id, db=db)

        if not user:
            raise UserNotFoundError()

        if verify_password(new_password, user.password):
            raise InvalidInputError(
                message="Password can't be the same as the old password"
            )

        set_password(
            user_object=get_user(user_id=verification_token.user_id, db=db),
            password=new_password,
        )
        db.delete(verification_token)
        db.commit()
