from datetime import datetime, timedelta, timezone
import hashlib
from secrets import token_urlsafe
import time
from typing import Optional
from uuid import UUID, uuid4

import jwt
from psycopg import InternalError, OperationalError
from sqlalchemy.orm import Session as DbSession

from api.config import (
    ACCESS_TOKEN_EXPIRE_SECONDS,
    ALGORITHM,
    REFRESH_TOKEN_EXPIRE_SECONDS,
    SECRET_KEY,
    VERIFICATION_TOKEN_EXPIRE_SECONDS,
)
from api.database import get_db_session
from api.models.auth import (
    RevokedAccessTokens,
    Tokens,
    User,
    VerificationTokenPurposes,
    VerificationTokens,
)
from api.schema.internal.auth import AccessTokenPayload, AuthTokens, IssuedRefreshToken
from api.schema.internal.errors import (
    BadRequestError,
    DependencyUnavailableError,
    RefreshTokenInvalidError,
    TokenExpiredError,
    TokenInvalidError,
    VerificationTokenInvalidError,
)

from api.logging_config import app_logger


def _ensure_timezone_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Ensure datetimes are timezone-aware in UTC
    """
    if dt is None:
        return dt

    if dt.tzinfo is None:
        # Add UTC timezone info
        return dt.replace(tzinfo=timezone.utc)

    return dt


def get_valid_refresh_token_entry(token: str, db: DbSession) -> Tokens:
    """Look up a raw refresh token and validate it's currently usable.

    Shared by both the cookie-based and body-based refresh flows in
    api/dependencies.py, which previously duplicated this lookup ->
    revoked-check -> expiry-check sequence independently. A fix here now
    covers both call sites automatically.

    Raises:
        RefreshTokenInvalidError: token not found, revoked, or expired.
        InternalError: token row is missing `expires_at`.

    Returns:
        The validated `Tokens` row.
    """
    token_hash = hash_token(token)
    token_entry = db.query(Tokens).filter(Tokens.token == token_hash).first()

    if not token_entry:
        raise RefreshTokenInvalidError()

    if token_entry.revoked:
        raise RefreshTokenInvalidError()

    expires_at = _ensure_timezone_aware(token_entry.expires_at)
    if not expires_at:
        app_logger.error(
            f"Tokens row with id {token_entry.id} has no `expires_at` column set"
        )
        raise InternalError()

    now = datetime.now(timezone.utc)
    if expires_at <= now:
        raise RefreshTokenInvalidError()

    return token_entry


# Create tokens


def _create_access_token(user_id: UUID) -> str:
    """
    Create new jwt access token for the user
    """
    expire: int = int(
        (
            datetime.now(tz=timezone.utc)
            + timedelta(seconds=ACCESS_TOKEN_EXPIRE_SECONDS)
        ).timestamp()
    )

    jti = uuid4()

    payload: dict[str, str | int] = {
        "sub": str(user_id),
        "exp": expire,
        "jti": str(jti),
    }

    token = str(jwt.encode(payload=payload, key=SECRET_KEY, algorithm=ALGORITHM))

    return token


def _create_refresh_token(user_id: UUID, db: DbSession) -> IssuedRefreshToken:
    """
    Create a new refresh token for given user_id
    """
    # Prepare token for db
    token = token_urlsafe(32)
    token_hash = hash_token(token)

    expires_at = datetime.now(tz=timezone.utc) + timedelta(
        seconds=REFRESH_TOKEN_EXPIRE_SECONDS
    )

    refresh_token_db_entry = Tokens(
        user_id=user_id,
        token=token_hash,
        expires_at=expires_at,
        created_at=datetime.now(tz=timezone.utc),
    )

    db.add(refresh_token_db_entry)
    db.flush()

    # Also return id for revocation purposes when rotating token
    return IssuedRefreshToken(token=token, id=refresh_token_db_entry.id)


def create_verification_token(
    user_id: UUID, purpose: VerificationTokenPurposes, db: DbSession
) -> str:
    # Check if account is already verified
    user_db_entry = db.get(User, user_id)
    if not user_db_entry or user_db_entry.verified:
        raise BadRequestError(detail="Email is already verified ")

    # Validate purpose
    if not purpose:
        app_logger.error(
            f"services/create_verification_token: Missing or incorrect purpose arg for user_id={user_id}"
        )
        raise InvalidInputError(
            message="Verification token purpose is required",
            detail={"field": "purpose"},
        )

    # Prepare vars for new db entry
    token = token_urlsafe(32)
    token_hash = hash_token(token)

    expires_at = datetime.now(tz=timezone.utc) + timedelta(
        seconds=VERIFICATION_TOKEN_EXPIRE_SECONDS
    )

    verification_token_db_entry = VerificationTokens(
        user_id=user_id,
        token=token_hash,
        purpose=purpose,
        expires_at=expires_at,
        created_at=datetime.now(tz=timezone.utc),
    )

    db.add(verification_token_db_entry)
    db.flush()
    return token


def _create_csrf_token() -> str:
    return token_urlsafe(32)


def _rotate_refresh_token(old_refresh_token: str, db: DbSession) -> IssuedRefreshToken:
    """
    Create a new refresh token and invalidate previous one
    """
    old_refresh_token_hash = hash_token(old_refresh_token)
    old_refresh_token_db_entry = (
        db.query(Tokens).filter(Tokens.token == old_refresh_token_hash).first()
    )

    # Check if old refresh token is still valid(exists, revoked, expired)
    if not old_refresh_token_db_entry:
        app_logger.warning("rotate_refresh_token: old token not found in DB")
        raise RefreshTokenInvalidError()

    if old_refresh_token_db_entry.revoked:
        # Possible refresh token replay: Revoke all active refresh tokens
        app_logger.warning(
            "rotate_refresh_token: old token already revoked, revoking all tokens for user_id=%s",
            old_refresh_token_db_entry.user_id,
        )
        revoke_all_refresh_tokens_for_user(
            user_id=old_refresh_token_db_entry.user_id, db=db
        )

        # Don't raise specific error so there is no information for attacker
        raise RefreshTokenInvalidError()

    expires_at = _ensure_timezone_aware(old_refresh_token_db_entry.expires_at)
    if not expires_at:
        app_logger.error(
            f"Tokens row with id {old_refresh_token_db_entry.id} has no `expires_at` column set"
        )
        raise InternalError()

    now = datetime.now(timezone.utc)
    if expires_at < now:
        app_logger.warning(
            f"rotate_refresh_token: old token expired (expires_at={expires_at}, now={now})"
        )
        raise TokenExpiredError()

    # If everything checks out, issue new refresh tokens and revoke old one
    new_refresh_token = _create_refresh_token(
        user_id=old_refresh_token_db_entry.user_id, db=db
    )
    app_logger.info(
        "rotate_refresh_token: created new refresh token (old_id=%s, new_id=%s, user_id=%s)",
        old_refresh_token_db_entry.id,
        new_refresh_token.id,
        old_refresh_token_db_entry.user_id,
    )

    revoke_refresh_token(
        token_id=new_refresh_token.id, replaced_by=new_refresh_token.id, db=db
    )
    app_logger.info(
        "rotate_refresh_token: revoked old token (id=%s, replaced_by=%s)",
        old_refresh_token_db_entry.id,
        new_refresh_token.id,
    )

    # Return full IssuedRefreshToken(with token id) so it's inline with create_refresh_token
    return new_refresh_token


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


### Verification


def verify_verification_token(
    token: str, purpose: VerificationTokenPurposes, db: DbSession
) -> VerificationTokens:
    # Fetch by hash and make sure it is not expired
    verification_token_db_entry = (
        db.query(VerificationTokens)
        .filter(
            VerificationTokens.token == hash_token(token),
            VerificationTokens.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )

    # Token doesn't exist or is expired
    if not verification_token_db_entry:
        raise VerificationTokenInvalidError()

    # Token purpose doens't match (password_reset vs email_verification)
    if verification_token_db_entry.purpose != purpose:
        raise VerificationTokenInvalidError()

    return verification_token_db_entry


def verify_token(token: str, token_hash: str) -> bool:
    return hash_token(token) == token_hash


def validate_access_token(token: str) -> AccessTokenPayload:
    """
    Decode and validate access token and return the claims(payload)
    """
    try:
        with get_db_session() as db:
            jwt_decoded = jwt.decode(jwt=token, key=SECRET_KEY, algorithms=[ALGORITHM])
            payload = AccessTokenPayload(**jwt_decoded)

            # Check revocation with one retry for transient db errors
            try:
                revoked_tokens = (
                    db.query(RevokedAccessTokens)
                    .filter(RevokedAccessTokens.jti == payload.jti)
                    .first()
                )
            except OperationalError as oe:
                app_logger.warning(
                    "OperationalError during token revocation check, retrying once: %s", oe
                )
                # Short wait to get rid of any transient errors
                time.sleep(0.05)
                try:
                    revoked_tokens = (
                        db.query(RevokedAccessTokens)
                        .filter(RevokedAccessTokens.jti == payload.jti)
                        .first()
                    )
                except OperationalError as oe2:
                    app_logger.exception(
                        "Database unavailable when validating access token: %s", oe2
                    )
                    # Consider DB unavailable — surface a 503-style error
                    raise DependencyUnavailableError()

            if revoked_tokens:
                raise jwt.InvalidTokenError()

            return payload

    except jwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except jwt.InvalidTokenError:
        raise TokenInvalidError()


### Revocation


def revoke_refresh_token(
    token_id: UUID, db: DbSession, replaced_by: Optional[UUID] = None
):
    revoke_time = datetime.now(timezone.utc)

    db.query(Tokens).filter(Tokens.id == token_id).update(
        values={
            Tokens.revoked_at: revoke_time,
            Tokens.revoked: True,
            Tokens.replaced_by: replaced_by,
        },
        synchronize_session=False,
    )
    db.flush()


def revoke_all_refresh_tokens_for_user(user_id: UUID, db: DbSession):
    revoke_time = datetime.now(timezone.utc)

    db.query(Tokens).filter(Tokens.user_id == user_id).update(
        values={Tokens.revoked_at: revoke_time, Tokens.revoked: True},
        synchronize_session=False,
    )
    db.flush()


def revoke_access_token(access_token: str, db: DbSession):
    payload = validate_access_token(access_token)
    revoked_token = RevokedAccessTokens(
        user_id=payload.sub,
        jti=payload.jti,
        expires_at=datetime.fromtimestamp(payload.exp, tz=timezone.utc),
    )
    db.add(revoked_token)
    db.flush()


### Main function


def issue_auth_tokens(
    user_id: UUID,
    old_refresh_token: Optional[str] = None,
    db: Optional[DbSession] = None,
) -> AuthTokens:
    """
    Create a new set of authentication tokens(access, refresh, csrf) and possibly take in old refresh token for rotation
    """

    def _issue_tokens_with_session(
        user_id: UUID, old_refresh_token: Optional[str], db: DbSession
    ) -> AuthTokens:
        new_access_token = _create_access_token(user_id)
        if old_refresh_token:
            new_refresh_token = _rotate_refresh_token(old_refresh_token, db)
        else:
            new_refresh_token = _create_refresh_token(user_id, db)
        new_csrf_token = _create_csrf_token()

        return AuthTokens(
            access_token=new_access_token,
            refresh_token=new_refresh_token.token,
            csrf_token=new_csrf_token,
        )

    if not db:
        with get_db_session() as db:
            try:
                issued_auth_tokens = _issue_tokens_with_session(
                    user_id=user_id, old_refresh_token=old_refresh_token, db=db
                )
                db.commit()
                return issued_auth_tokens
            except Exception:
                db.rollback()
                raise

    return _issue_tokens_with_session(
        user_id=user_id, old_refresh_token=old_refresh_token, db=db
    )
