from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable, Optional, ParamSpec, TypeVar, cast
from uuid import UUID

from fastapi import Request, WebSocket
from fastapi.requests import HTTPConnection
from sqlalchemy.orm import Session as DbSession

from api.limiter import limiter
from api.database import get_db_session
from api.models.auth import Tokens, User
from api.schema.internal.auth import AuthTokens
from api.schema.internal.errors import (
    AccountNotVerifiedError,
    BadRequestError,
    ForbiddenError,
    RefreshTokenInvalidError,
    RefreshTokenMissingError,
    TokenExpiredError,
    TokenInvalidError,
    TokenMissingError,
)
from api.services.auth.cookies import (
    check_csrf,
    get_access_token_cookie,
    get_refresh_token_cookie,
)
from api.services.auth.tokens import (
    get_valid_refresh_token_entry,
    issue_auth_tokens,
    validate_access_token,
)


def get_email_from_user_id(user_id: UUID, db: DbSession) -> Optional[str]:
    return db.query(User.email).filter(User.id == user_id).scalar()


def get_user_id_from_email(email: str, db: DbSession) -> Optional[UUID]:
    return db.query(User.id).filter(User.email == email).scalar()


def get_user_id(connection: HTTPConnection, skip_csrf: bool = False) -> UUID:
    # CHeck csrf
    if (
        not isinstance(connection, WebSocket)  # Allow websocket without csrf
        and not check_csrf(connection=connection)  # Check csrf
        and not skip_csrf  # Csrf check failed
    ):
        raise ForbiddenError(detail="CSRF token is invalid")

    access_token = get_access_token_cookie(connection=connection)
    if not access_token:
        raise TokenMissingError()

    with get_db_session() as db:
        payload = validate_access_token(token=access_token, db=db)

        user_id = payload.sub
        if not user_id:
            raise BadRequestError("User ID missing from access token payload")

        # Import lazily to avoid module-level circular imports between auth deps and accounts.
        from api.services.auth.accounts import user_is_verified

        # Check if account is verified
        account_verified = user_is_verified(user_id=user_id, db=db)

        if not account_verified:
            raise AccountNotVerifiedError()

    return user_id


def get_user_id_skip_csrf(connection: HTTPConnection):
    """
    Wrapper for get_user_id. In a FastAPI dependency, args can not be passed, for that reason this wrapper exists
    """
    return get_user_id(connection=connection, skip_csrf=True)


def get_user_id_from_refresh(
    connection: HTTPConnection, skip_csrf: bool = False
) -> Optional[tuple[UUID, str]]:
    token = get_refresh_token_cookie(connection)
    if not token:
        return None

    if (
        not isinstance(connection, WebSocket)
        and not check_csrf(connection=connection)
        and not skip_csrf
    ):
        raise ForbiddenError(detail="CSRF token is invalid")

    with get_db_session() as db:
        token_entry = get_valid_refresh_token_entry(token, db)
        return (token_entry.user_id, token)


def get_user_id_from_refresh_body(token: str) -> UUID:
    with get_db_session() as db:
        token_entry = get_valid_refresh_token_entry(token, db)
        return token_entry.user_id


def validate_user(
    request: Request, db: DbSession, allow_refresh: bool = True
) -> tuple[Optional[UUID], Optional[AuthTokens]]:
    """Validate a user by checking their access token, falling back to a
    refresh-token-based re-issue when the access token is missing/expired."""
    try:
        access_token = request.cookies.get("access_token")
        try:
            if access_token is None:
                raise TokenMissingError()
            payload = validate_access_token(access_token, db=db)
            return payload.sub, None
        except (TokenExpiredError, TokenMissingError):
            if not allow_refresh:
                raise TokenMissingError()

            try:
                data = get_user_id_from_refresh(request, skip_csrf=True)
                if not data:
                    raise RefreshTokenMissingError()
                user_id, raw_refresh = data

                tokens = issue_auth_tokens(
                    user_id=user_id, old_refresh_token=raw_refresh, db=db
                )
                return user_id, tokens
            except (
                RefreshTokenMissingError,
                RefreshTokenInvalidError,
                ForbiddenError,
                TokenExpiredError,
                TokenMissingError,
            ):
                return None, None
    except (TokenExpiredError, TokenMissingError, TokenInvalidError):
        return None, None
    except Exception:
        return None, None


async def cleanup_tokens() -> None:
    grace_period = datetime.now(tz=timezone.utc) - timedelta(days=7)

    with get_db_session() as db:
        db.query(Tokens).filter(
            (Tokens.expires_at < datetime.now(tz=timezone.utc))
            | (
                # (Tokens.revoked == True) &
                (Tokens.revoked_at.isnot(other=None))
                & (Tokens.revoked_at < grace_period)
            )
        ).delete(synchronize_session=False)
        db.commit()

P = ParamSpec("P")
R = TypeVar("R")
_untyped_limit = getattr(limiter, "limit")

def typed_limit(
    *args: Any, **kwargs: Any
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        wrapped = _untyped_limit(*args, **kwargs)(func)
        return wraps(func)(wrapped)

    return cast(Callable[[Callable[P, R]], Callable[P, R]], decorator)
