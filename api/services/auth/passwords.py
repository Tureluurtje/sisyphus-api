import argon2
from typing import Optional
import zxcvbn

from api.schema.internal.errors import InvalidInputError
from api.models.auth import User


from api.config import MIN_PASSWORD_ZXCVBN_SCORE

_ph = argon2.PasswordHasher()


def validate_password_strength(password: str, email: Optional[str] = None) -> None:
    user_inputs = [email] if email else []
    if len(password) > 72:
        raise InvalidInputError(detail="Password cannot be longer than 72 characters")

    result = zxcvbn.zxcvbn(password, user_inputs=user_inputs)
    score = result.get("score", 0)

    if score < MIN_PASSWORD_ZXCVBN_SCORE:
        feedback = result.get("feedback", {})
        raise InvalidInputError(
            message="Password is too weak",
            detail={
                "field": "password",
                "score": score,
                "min_score": MIN_PASSWORD_ZXCVBN_SCORE,
                "warning": feedback.get("warning"),
                "suggestions": feedback.get("suggestions", []),
            },
        )


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return _ph.verify(password=password, hash=hashed_password)
    except argon2.exceptions.VerifyMismatchError:
        return False


def hash_password(password: str) -> str:
    return _ph.hash(password)


def set_password(user_object: User, password: str):
    validate_password_strength(password)

    user_object.password = hash_password(password)
