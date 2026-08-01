from fastapi import Response, Cookie, Request
from fastapi.responses import JSONResponse
from datetime import date, datetime, timedelta, timezone
from starlette.requests import HTTPConnection
from starlette.websockets import WebSocket
from sqlalchemy import and_, func
from sqlalchemy.exc import IntegrityError, OperationalError
import logging
import time
from sqlalchemy.orm.session import Session
import jwt  # type: ignore[reportUnknownMemberType]
import hashlib
import resend
import importlib
from uuid import UUID, uuid4
from typing import Optional, Any
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError, VerifyMismatchError
from secrets import token_urlsafe

from api.models.words import Cards, Reviews
from api.schema.internal.errors import (
    AccountNotVerifiedError,
    BadRequestError,
    ConflictError,
    DependencyUnavailableError,
    ForbiddenError,
    InternalError,
    InvalidCredentialsError,
    InvalidInputError,
    RefreshTokenInvalidError,
    RefreshTokenMissingError,
    TokenExpiredError,
    TokenInvalidError,
    TokenMissingError,
    UserNotFoundError,
    VerificationTokenInvalidError,
)
from api.schema.internal.users import UserProfileDetail
from api.schema.internal.auth import EmailData

from api.database import get_db_session
from api.models.auth import (
    User,
    Tokens,
    RevokedAccessTokens,
    VerificationTokens,
    VerificationTokenPurposes,
)
from api.schema.internal.auth import (
    AccessTokenPayload,
    ReturnTokens,
    IssuedRefreshToken,
)

from api.config import (
    SECRET_KEY,
    ALGORITHM,
    SECURE_COOKIES,
    MIN_PASSWORD_ZXCVBN_SCORE,
    ACCESS_TOKEN_EXPIRE_SECONDS,
    REFRESH_TOKEN_EXPIRE_SECONDS,
    VERIFICATION_TOKEN_EXPIRE_SECONDS,
    RESEND_API_KEY,
    HOST,
    PORT,
)

from api.logging_config import app_logger, error_logger

# Initialize argon2 PasswordHasher instance
_ph = PasswordHasher()
resend.api_key = RESEND_API_KEY

#########################################################
###                     HELPERS                       ###
#########################################################


def _ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime is timezone-aware in UTC.

    Many stored datetimes may be naive (no tzinfo). Treat naive values as
    UTC to allow consistent comparisons with timezone-aware `now()`.
    """
    if dt is None:
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _get_email_from_user_id(
    user_id: UUID, db: Optional[Session] = None
) -> Optional[str]:
    if db:
        result = db.query(User.email).where(User.id == user_id).scalar()
    else:
        with get_db_session() as db:
            result = db.query(User.email).where(User.id == user_id).scalar()

    if result is None:
        app_logger.warning(f"Email not found for user id {user_id}")
    return result


def validate_password_strength(password: str, email: Optional[str] = None) -> None:
    """Validate that password strenght is good measured with zxcvbn library

    Args:
        password (str): Password to check
        email (Optional[str], optional): Optional email to check with the password. Defaults to None.

    Raises:
        InvalidInputError: Password is longer than 72 characters
        DependencyUnavailableError: zxcvbn dependency not installed/ not available
        InvalidInputError: Password is too weak(not level given in `.env` file)
    """
    user_inputs = [email] if email else []
    if len(password) > 72:
        raise InvalidInputError(detail="Password cannot be longer than 72 characters")
    try:
        zxcvbn_module = importlib.import_module("zxcvbn")
        zxcvbn_fn = getattr(zxcvbn_module, "zxcvbn")
    except (ImportError, AttributeError):
        raise DependencyUnavailableError(
            message="Password scoring dependency unavailable"
        )

    result = zxcvbn_fn(password, user_inputs=user_inputs)
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


def get_user_review_streak(user_id: UUID, db: Session) -> int:
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


def get_user(user_id: UUID, db: Session) -> User:
    user = db.get(User, user_id)

    if not user:
        app_logger.error(msg=f"User not found for id {user_id} from users table")
        raise UserNotFoundError()

    return user


#########################################################
###                     TOKENS                        ###
#########################################################


def create_tokens_service(
    user_id: UUID, db: Optional[Session] = None, old_refresh_token: Optional[str] = None
) -> ReturnTokens:
    """Issue new tokens pair, possibly rotating the old refresh token

    Args:
        user_id (UUID): The user id of the user
        db (Optional[Session], optional): Optional sqlalchemy `Session` object. Defaults to None.
        old_refresh_token (Optional[str], optional): The optional old refresh token. If given, gets revoked(rotated). Defaults to None.

    Returns:
        ReturnTokens: The new, valid refresh, access and csrf tokens wrapped in a `ReturnTokens` object
    """

    def create_access_token(user_id: UUID) -> str:
        """Create a new valid access token for a given user id

        Args:
            user_id (UUID): The user id of the user for who to generate the token

        Returns:
            str: The valid, newly build access token for the user with the given id
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

        token = str(jwt.encode(payload=payload, key=SECRET_KEY, algorithm=ALGORITHM))  # type: ignore[reportUnknownMemberType]
        return token

    def create_refresh_token(user_id: UUID, db: Session) -> IssuedRefreshToken:
        """Create a new, valid refresh token for the given user id

        Args:
            user_id (UUID): The user id of the user
            db (Session): Sqlalchemy `Session` object, this session is used to create the refresh token

        Returns:
            IssuedRefreshToken: The issued refresh token, wrapped in a `IssuedRefreshToken` object
        """

        token = token_urlsafe(32)

        token_hash = hash_token(token=token)
        expires_at = datetime.now(tz=timezone.utc) + timedelta(
            seconds=REFRESH_TOKEN_EXPIRE_SECONDS
        )
        token_entry = Tokens(
            user_id=user_id,
            token=token_hash,
            expires_at=expires_at,
            created_at=datetime.now(tz=timezone.utc),
        )
        db.add(instance=token_entry)
        db.flush()
        return IssuedRefreshToken(token=token, id=token_entry.id)

    def rotate_refresh_token(old_refresh_token: str, db: Session) -> IssuedRefreshToken:
        """rotate a valid refresh token and issue a new one

        Args:
            old_refresh_token (str): The old, valid refresh token
            db (Session): The active sqlalchemy `Session` object

        Raises:
            RefreshTokenInvalidError: Old refresh token is not found in the db
            RefreshTokenInvalidError: Old refresh token is invalid
            InternalError: No expires at column for old refresh token row
            TokenExpiredError: Old refresh token is expired

        Returns:
            IssuedRefreshToken: The newly issued refresh token, wrapped in an `IssuedRefreshToken` object
        """
        logger = logging.getLogger(__name__)
        token_hash = hash_token(token=old_refresh_token)
        token_entry = db.query(Tokens).filter(Tokens.token == token_hash).first()

        if not token_entry:
            logger.warning("rotate_refresh_token: old token not found in DB")
            raise RefreshTokenInvalidError()

        if token_entry.revoked:
            # Attempted refresh with revoked token (possible replay):
            # revoke all active refresh tokens for this user in one query.
            logger.warning(
                "rotate_refresh_token: old token already revoked, revoking all tokens for user_id=%s",
                token_entry.user_id,
            )
            revoke_refresh_token(user_id=token_entry.user_id, db=db)

            raise RefreshTokenInvalidError()

        # Normalize stored datetime to timezone-aware before comparing. Some
        # existing DB rows may contain naive datetimes; treat those as UTC.
        expires_at = _ensure_aware(token_entry.expires_at)
        if not expires_at:
            app_logger.error(
                f"Tokens row with id {token_entry.id} has no `expires_at` column set"
            )
            raise InternalError()

        now = datetime.now(timezone.utc)
        if expires_at <= now:
            logger.warning(
                "rotate_refresh_token: old token expired (expires_at=%s, now=%s)",
                expires_at,
                now,
            )
            raise TokenExpiredError()

        # Issue new token
        new_refresh_token = create_refresh_token(user_id=token_entry.user_id, db=db)
        logger.info(
            "rotate_refresh_token: created new refresh token (old_id=%s, new_id=%s, user_id=%s)",
            token_entry.id,
            new_refresh_token.id,
            token_entry.user_id,
        )

        # Revoke old
        revoke_refresh_token(
            token_id=token_entry.id, replaced_by=new_refresh_token.id, db=db
        )
        logger.info(
            "rotate_refresh_token: revoked old token (id=%s, replaced_by=%s)",
            token_entry.id,
            new_refresh_token.id,
        )

        return new_refresh_token

    def create_csrf_token() -> str:
        """Create a new csrf token

        Returns:
            str: The newly created csrf token
        """
        return token_urlsafe(32)

    def issue_tokens_with_session(session: Session) -> ReturnTokens:
        """Issue new token pair with active db session

        Args:
            session (Session): active sqlalchemy `Session` object

        Returns:
            ReturnTokens: The wrapped tokens(access, refresh and csrf)
        """
        new_access_token = create_access_token(user_id=user_id)
        if old_refresh_token:
            new_refresh_token = rotate_refresh_token(old_refresh_token, session)
        else:
            new_refresh_token = create_refresh_token(user_id, session)
        new_csrf_token = create_csrf_token()
        return ReturnTokens(
            refresh_token=new_refresh_token.token,
            access_token=new_access_token,
            csrf_token=new_csrf_token,
        )

    if db is not None:
        return issue_tokens_with_session(db)

    with get_db_session() as local_db:
        try:
            tokens = issue_tokens_with_session(local_db)
            local_db.commit()
            return tokens
        except Exception:
            local_db.rollback()
            raise


def create_verification_token(
    user_id: UUID, purpose: VerificationTokenPurposes, db: Optional[Session] = None
) -> str:
    """Create a unique verification token for email verification.

    The function generates a random token string, hashes it, and stores the
    hash in the database associated with the user ID. The raw token is returned
    for sending to the user.

    Args:
        user_id: UUID of the user for whom the verification token is issued.
        db: Optional SQLAlchemy session to use for persistence.

    Returns:
        The raw verification token string.

    Raises:
        sqlalchemy.exc.IntegrityError: If a database constraint is violated
            while creating the token record (propagates after rollback).
    """
    token = token_urlsafe(32)
    token_hash = hash_token(token=token)

    # Validate presence
    if not purpose:
        app_logger.error(
            "create_verification_token: missing or empty 'purpose' for user_id=%s",
            user_id,
        )
        raise InvalidInputError(
            message="Verification token purpose is required",
            detail={"field": "purpose"},
        )

    expires_at = datetime.now(tz=timezone.utc) + timedelta(
        seconds=VERIFICATION_TOKEN_EXPIRE_SECONDS
    )

    token_entry = VerificationTokens(
        user_id=user_id,
        token=token_hash,
        purpose=purpose,
        expires_at=expires_at,
        created_at=datetime.now(tz=timezone.utc),
    )

    if db is not None:
        db.add(instance=token_entry)
        db.flush()
        return token
    else:
        with get_db_session() as db:
            try:
                db.add(instance=token_entry)
                db.commit()
                return token
            except Exception:
                db.rollback()
                raise
            raise InternalError()


def hash_token(token: str) -> str:
    """Compute a SHA-256 hash for a token

    Args:
        token (str): The token to hash

    Returns:
        str: The hashed token
    """
    return hashlib.sha256(token.encode()).hexdigest()


def verify_token(token: str, token_hash: str) -> bool:
    """Verify a token by hashing it and comparing the hash

    Args:
        token (str): The token to compare with
        token_hash (str): The token hash to compare to

    Returns:
        bool: Whether the provided token and token hash match
    """
    return hash_token(token) == token_hash


async def cleanup_tokens() -> None:
    """Remove expired or revoked refresh tokens from persistent storage.

    The function opens a new database session and deletes any ``Tokens``
    records that are either expired (``expires_at`` in the past) or revoked
    longer than the grace period. This is intended as a maintenance task and
    does not return a value.
    """
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


#########################################################
###                     COOKIES                       ###
#########################################################


def response_cookies_generator(
    tokens: ReturnTokens | dict[str, str], response: Response | None = None
) -> Response:
    """Set authentication cookies on a response.

    Accept either a `ReturnTokens` pydantic model or a plain `dict` (the
    web proxy code returns JSON). This prevents subscription/attribute
    errors when different call sites provide different types.
    """

    # Normalise token access for model or mapping
    def _get(key: str):
        if hasattr(tokens, key):
            return getattr(tokens, key)
        if isinstance(tokens, dict):
            return tokens.get(key)
        return None

    csrf = _get("csrf_token")
    access = _get("access_token")
    refresh = _get("refresh_token")

    if response is None:
        response = JSONResponse(
            status_code=200, content={"success": True, "csrf_token": csrf}
        )

    app_logger.info(
        f"response_cookies_generator: setting cookies (access={access is not None}, refresh={refresh is not None}, csrf={csrf is not None})"
    )

    if access is not None:
        response.set_cookie(
            key="access_token",
            value=access,
            httponly=True,
            secure=SECURE_COOKIES,
            samesite="none",
            max_age=int(ACCESS_TOKEN_EXPIRE_SECONDS),
            path="/",
        )
        app_logger.debug(
            f"response_cookies_generator: set access_token cookie (secure={SECURE_COOKIES}, max_age={ACCESS_TOKEN_EXPIRE_SECONDS})"
        )

    if refresh is not None:
        response.set_cookie(
            key="refresh_token",
            value=refresh,
            httponly=True,
            secure=SECURE_COOKIES,
            samesite="none",
            max_age=int(REFRESH_TOKEN_EXPIRE_SECONDS),
            path="/",
        )
        app_logger.debug(
            f"response_cookies_generator: set refresh_token cookie (secure={SECURE_COOKIES}, max_age={REFRESH_TOKEN_EXPIRE_SECONDS})"
        )

    if csrf is not None:
        response.set_cookie(
            key="csrf_token",
            value=csrf,
            httponly=False,
            secure=SECURE_COOKIES,
            samesite="none",
            max_age=int(REFRESH_TOKEN_EXPIRE_SECONDS),
            path="/",
        )
        app_logger.debug(f"response_cookies_generator: set csrf_token cookie")

    return response


def apply_refreshed_token_cookies(
    connection: HTTPConnection, response: Response
) -> Response:
    """Apply refreshed auth cookies captured during dependency auth checks.

    When dependencies set cookies on FastAPI's injected Response object, those
    cookies are not automatically carried over if a route returns a custom
    Response/JSONResponse instance. This helper bridges that gap by copying
    pending refreshed tokens from request state onto the returned response.
    """
    tokens = getattr(connection.state, "refreshed_tokens", None)
    if tokens is not None:
        response_cookies_generator(response=response, tokens=tokens)
    return response


def clear_token_cookies_service(response: Response) -> None:
    """Set the authentication cookies(access token, refresh token and csrf token) to a `max_age` of 0 what makes it that the cookie expires immediately"""
    response.set_cookie(
        key="access_token",
        value="",
        httponly=True,
        secure=SECURE_COOKIES,
        samesite="none",
        path="/",
        max_age=0,
    )

    response.set_cookie(
        key="refresh_token",
        value="",
        httponly=True,
        secure=SECURE_COOKIES,
        samesite="none",
        path="/",
        max_age=0,
    )

    response.set_cookie(
        key="csrf_token",
        value="",
        secure=SECURE_COOKIES,
        samesite="none",
        path="/",
        max_age=0,
    )


def get_access_token_cookie(
    connection: HTTPConnection, access_token: Optional[str] = Cookie(default=None)
) -> Optional[str]:
    """Dependency to retrieve the access token injected by FastAPI in the connection object

    Args:
        connection (HTTPConnection): `HTTPConnection` object injected by FastAPI which includes the possible access token cookie
        access_token (Optional[str], optional): Possible injected access token cookie by FastAPI. Defaults to Cookie(default=None).

    Returns:
        Optional[str]: The optionally, by FastAPI, injected access token by
    """
    if isinstance(access_token, str) and access_token:
        return access_token

    cookie_token = connection.cookies.get("access_token")
    if cookie_token:
        return cookie_token

    if isinstance(connection, WebSocket):
        return get_access_token_cookie_fallback(connection)

    return None


def get_access_token_cookie_fallback(connection: HTTPConnection) -> Optional[str]:
    """Fallback to the `get_access_token_cookie` function. This function tries to take the access token from the Authorization Bearer token header"""
    auth_header = connection.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]

    token = connection.query_params.get("token")
    if token:
        return token

    return None


def get_refresh_token_cookie(
    connection: HTTPConnection, refresh_token: Optional[str] = Cookie(default=None)
) -> Optional[str]:
    if not isinstance(refresh_token, str):
        return connection.cookies.get("refresh_token")
    return refresh_token


#########################################################
###                     PASSWORDS                     ###
#########################################################


def check_csrf(connection: HTTPConnection) -> bool:
    try:
        return connection.cookies.get("csrf_token") == connection.headers.get(
            "X-CSRF-Token"
        )
    except AttributeError:
        return False


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2 hashed password.

    Args:
        plain_password: The plaintext password provided by the user.
        hashed_password: The stored Argon2 hash to verify against.

    Returns:
        True if the password matches the hash, otherwise False.

    Raises:
        argon2.exceptions.VerifyMismatchError: If the hash does not match the
            supplied password.
        argon2.exceptions.VerificationError: If there is a problem verifying the
            hash (for example a corrupted hash).
    """
    try:
        result = _ph.verify(hash=hashed_password, password=plain_password)
        return result
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def hash_password(password: str) -> str:
    """Create an Argon2 hash for a plaintext password.

    Args:
        password: The plaintext password to hash.

    Returns:
        The Argon2 hashed password as a string suitable for storage.
    """
    return _ph.hash(password=password)


def set_password(
    user: User,
    new_password: str,
) -> None:
    # Reset password
    validate_password_strength(password=new_password, email=user.email)

    # Hash the new password and patch the user instance
    user.password = hash_password(password=new_password)


def change_password(
    user_id: UUID, old_password: str, new_password: str, db: Session
) -> None:
    user = db.get(User, user_id)

    if not user:
        app_logger.error(msg=f"User not found for id {user_id} from users table")
        raise UserNotFoundError()

    # Check old password
    if not verify_password(plain_password=old_password, hashed_password=user.password):
        raise InvalidCredentialsError()

    # Reset password
    set_password(new_password=new_password, user=user)
    db.flush()


#########################################################
###                       MAIN                        ###
#########################################################


def authenticate_user(email: str, password: str) -> ReturnTokens:
    """Authenticate a user and return a new access and refresh token pair.

    The function verifies credentials against the stored user record. On
    success it issues a short-lived access token and a persisted refresh
    token.

    Args:
        email: The user's email address used to locate the account.
        password: The plaintext password to verify.

    Returns:
        A dict with keys ``access_token`` and ``refresh_token`` containing
        newly issued tokens.

    Raises:
        fastapi.HTTPException: If credentials are invalid (HTTP 401).
    """
    with get_db_session() as db:
        user = db.query(User).filter(User.email == email).first()
        if not user or not verify_password(
            plain_password=password, hashed_password=user.password
        ):
            raise InvalidCredentialsError()

        if user.verified == False:
            raise AccountNotVerifiedError()

        new_tokens = create_tokens_service(
            user_id=user.id,
            db=db,
        )
        db.commit()

        return new_tokens


def register_user(username: str, grade: int, email: str, password: str) -> ReturnTokens:
    """Create a new user account and associated profile, returning tokens.

    The function creates a user record with an Argon2-hashed password and a
    corresponding profile row populated from ``profile_data`` when provided.
    On successful creation it issues and returns an access and refresh token
    pair.

    Args:
        email: Email address for the new account.
        password: Plaintext password which will be hashed for storage.

    Returns:
        A dict containing ``access_token`` and ``refresh_token`` for the new
        user.

    Raises:
        fastapi.HTTPException: If the email is already registered
            (HTTP 409).
    """
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

            new_tokens = create_tokens_service(user_id=new_user.id, db=db)

            send_account_verification_email_service(user_id=new_user.id, db=db)

            db.commit()

            return new_tokens

        except IntegrityError as e:
            db.rollback()  # if email or username is already in use
            if "username" in str(e.args):
                raise ConflictError(message="duplicate username")
            else:
                raise ConflictError(message="duplicate email")


def validate_access_token(token: str) -> AccessTokenPayload:
    """Decode and validate a JWT access token, returning its claims.

    Args:
        token: The JWT access token string to validate.

    Returns:
        An ``AccessTokenPayload`` object constructed from the token payload.

    Raises:
        fastapi.HTTPException: If the token is invalid or expired
            (HTTP 401).
    """
    logger = logging.getLogger(__name__)
    try:
        jwt_decoded = jwt.decode(jwt=token, key=SECRET_KEY, algorithms=[ALGORITHM])  # type: ignore[reportUnknownMemberType]
        payload = AccessTokenPayload(**jwt_decoded)

        # Check revocation, with a single retry for transient DB errors
        try:
            with get_db_session() as db:
                token_entry = (
                    db.query(RevokedAccessTokens)
                    .filter(RevokedAccessTokens.jti == payload.jti)
                    .first()
                )
        except OperationalError as oe:
            logger.warning(
                "OperationalError during token revocation check, retrying once: %s", oe
            )
            time.sleep(0.05)
            try:
                with get_db_session() as db:
                    token_entry = (
                        db.query(RevokedAccessTokens)
                        .filter(RevokedAccessTokens.jti == payload.jti)
                        .first()
                    )
            except OperationalError as oe2:
                logger.exception(
                    "Database unavailable when validating access token: %s", oe2
                )
                # Consider DB unavailable — surface a 503-style error
                raise DependencyUnavailableError()

        if token_entry:
            raise jwt.InvalidTokenError

        return payload
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except jwt.InvalidTokenError:
        raise TokenInvalidError()


def delete_account_service(user_id: UUID) -> None:
    with get_db_session() as db:
        user_to_delete = db.query(User).where(User.id == user_id).scalar()
        if not user_to_delete:
            raise BadRequestError(detail=f"User with id {user_id} not found")
        db.delete(user_to_delete)
        db.commit()


def revoke_refresh_token(
    user_id: Optional[UUID] = None,
    token_id: Optional[UUID] = None,
    replaced_by: Optional[UUID] = None,
    db: Optional[Session] = None,
) -> None:
    """Revoke all stored refresh tokens for a given user by updating revoked_at."""
    if user_id is None and token_id is None:
        raise InternalError()

    # Prefer checking the `revoked` boolean flag rather than `revoked_at`.
    # This avoids edge cases where `revoked_at` may be NULL but `revoked` is
    # already set, and is clearer about intent: we only want non-revoked rows.
    conditions: list[Any] = [Tokens.revoked.is_(False)]
    if user_id is not None:
        conditions.append(Tokens.user_id == user_id)
    if token_id is not None:
        conditions.append(Tokens.id == token_id)

    revoke_time = datetime.now(tz=timezone.utc)

    if db is not None:
        db.query(Tokens).filter(and_(*conditions)).update(
            values={
                Tokens.revoked_at: revoke_time,
                Tokens.revoked: True,
                Tokens.replaced_by: replaced_by,
            },
            synchronize_session=False,
        )
        db.flush()
        return None

    with get_db_session() as local_db:
        local_db.query(Tokens).filter(and_(*conditions)).update(
            values={
                Tokens.revoked_at: revoke_time,
                Tokens.revoked: True,
                Tokens.replaced_by: replaced_by,
            },
            synchronize_session=False,
        )
        local_db.commit()


def revoke_access_token(access_token: str) -> None:
    payload = validate_access_token(access_token)
    with get_db_session() as db:
        revoked_token = RevokedAccessTokens(
            user_id=payload.sub,
            jti=payload.jti,
            expires_at=datetime.fromtimestamp(payload.exp, tz=timezone.utc),
        )
        db.add(revoked_token)
        db.commit()


def get_user_data_service(user_id: UUID) -> UserProfileDetail:
    """Retrieve user profile data by user ID."""
    with get_db_session() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise BadRequestError("User not found")
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


def get_user_id(
    connection: HTTPConnection,
    skip_csrf: bool = False,
) -> UUID:
    """Extract the user UUID from an access token supplied in a request.

    The function attempts to retrieve a bearer token using
    :pyfunc:`get_access_token`, validates it and returns the subject value as
    a UUID string. HTTP exceptions are raised for missing or malformed
    tokens.

    Args:
        connection: HTTP request/websocket connection.
        skip_csrf: Disable CSRF checks (internal use only).

    Returns:
        The user identifier (UUID) present in the validated token payload.

    Raises:
        fastapi.HTTPException: If no token is provided or the token payload
            does not include a user identifier.
    """
    # Check csrf first
    if (
        not isinstance(connection, WebSocket)
        and not check_csrf(connection=connection)
        and not skip_csrf
    ):
        raise ForbiddenError(detail="CSRF token is invalid")

    token = get_access_token_cookie(connection=connection)
    if not token:
        """
        refresh_user_id, refresh_token = get_user_id_from_refresh(
            connection=connection,
            skip_csrf=skip_csrf,
        )
        tokens = create_tokens_service(
            user_id=refresh_user_id, old_refresh_token=refresh_token
        )

        # Store refreshed tokens on request state so custom Response-returning
        # routes can apply them before returning.
        try:
            connection.state.refreshed_tokens = tokens
        except Exception:
            pass

        token = tokens.access_token
        """
        raise TokenMissingError()

    payload = validate_access_token(token=token)

    user_id = payload.sub
    if not user_id:
        raise InternalError()
    return user_id


def get_user_id_skip_csrf(connection: HTTPConnection):
    """Wrapper for `get_user_id` function for non state changing routes.

    Args:
        connection (HTTPConnection): The, by FastAPI injected, connection
    """
    return get_user_id(connection=connection, skip_csrf=True)


def get_user_id_from_refresh(
    connection: HTTPConnection, skip_csrf: bool = False
) -> Optional[tuple[UUID, str]]:
    logger = logging.getLogger(__name__)
    token = get_refresh_token_cookie(connection)

    if not token:
        return None

    if (
        not isinstance(connection, WebSocket)
        and not check_csrf(connection=connection)
        and not skip_csrf
    ):
        logger.warning(
            "get_user_id_from_refresh: CSRF check failed, skip_csrf=%s", skip_csrf
        )
        raise ForbiddenError(detail="CSRF token is invalid")

    with get_db_session() as db:
        token_hash = hash_token(token)
        token_entry = db.query(Tokens).where(Tokens.token == token_hash).first()
        if not token_entry:
            logger.warning(
                "get_user_id_from_refresh: token not found in DB (hash=%s)",
                token_hash[:8],
            )
            raise RefreshTokenInvalidError()
        if token_entry.revoked:
            logger.warning(
                "get_user_id_from_refresh: token is revoked (user_id=%s, revoked_at=%s)",
                token_entry.user_id,
                token_entry.revoked_at,
            )
            raise RefreshTokenInvalidError()
        # Normalize stored datetime to timezone-aware for comparison.
        expires_at = _ensure_aware(token_entry.expires_at)
        if not expires_at:
            app_logger.error(
                f"Tokens row with id {token_entry.id} has no `expires_at` column set"
            )
            raise InternalError()

        now = datetime.now(timezone.utc)
        if expires_at <= now:
            logger.warning(
                "get_user_id_from_refresh: token expired (expires_at=%s, now=%s)",
                expires_at,
                now,
            )
            raise RefreshTokenInvalidError()
        logger.info(
            "get_user_id_from_refresh: token valid for user_id=%s, expires_at=%s",
            token_entry.user_id,
            expires_at,
        )
        return (token_entry.user_id, token)


def get_user_id_from_refresh_body(token: str) -> UUID:
    logger = logging.getLogger(__name__)
    with get_db_session() as db:
        token_hash = hash_token(token)
        token_entry = db.query(Tokens).where(Tokens.token == token_hash).first()
        if not token_entry:
            logger.warning(
                "get_user_id_from_refresh_body: token not found in DB (hash=%s)",
                token_hash[:8],
            )
            raise RefreshTokenInvalidError()
        if token_entry.revoked:
            logger.warning(
                "get_user_id_from_refresh_body: token is revoked (user_id=%s, revoked_at=%s)",
                token_entry.user_id,
                token_entry.revoked_at,
            )
            raise RefreshTokenInvalidError()
        # Normalize stored datetime to timezone-aware for comparison.
        expires_at = _ensure_aware(token_entry.expires_at)
        if not expires_at:
            app_logger.error(
                f"Tokens row with id {token_entry.id} has no `expires_at` column set"
            )
            raise InternalError()

        now = datetime.now(timezone.utc)
        if expires_at <= now:
            logger.warning(
                "get_user_id_from_refresh_body: token expired (expires_at=%s, now=%s)",
                expires_at,
                now,
            )
            raise RefreshTokenInvalidError()
        logger.info(
            "get_user_id_from_refresh_body: token valid for user_id=%s, expires_at=%s",
            token_entry.user_id,
            expires_at,
        )
        return token_entry.user_id


def validate_user_service(
    request: Request,
    allow_refresh: bool = True,
) -> tuple[Optional[UUID], Optional[ReturnTokens]]:
    """Validate user by checking their access token."""
    try:
        access_token = request.cookies.get("access_token")
        app_logger.info(
            f"validate_user: access_token present={access_token is not None}, allow_refresh={allow_refresh}"
        )
        try:
            if access_token is None:
                raise TokenMissingError()
            payload = validate_access_token(access_token)
            return payload.sub, None
        except (TokenExpiredError, TokenMissingError) as exc:
            app_logger.info(
                f"validate_user: access token missing/expired, attempting refresh. Exception: {type(exc).__name__}"
            )
            # Only try refresh when token expired and refresh allowed
            # Allow refresh attempt when token expired or missing (refresh token may still exist)
            if not allow_refresh:
                app_logger.info(
                    "validate_user: refresh not allowed, raising TokenMissingError"
                )
                raise TokenMissingError()

            try:
                app_logger.info(
                    "validate_user: attempting to refresh using refresh_token cookie"
                )
                data = get_user_id_from_refresh(request, skip_csrf=True)
                if not data:
                    raise RefreshTokenMissingError()
                user_id, raw_refresh = data

                app_logger.info(
                    f"validate_user: refresh_token lookup successful, user_id={user_id}"
                )
                tokens = create_tokens_service(
                    user_id=user_id, old_refresh_token=raw_refresh
                )
                app_logger.info(
                    f"validate_user: new tokens created successfully for user_id={user_id}"
                )
                return user_id, tokens
            except (
                RefreshTokenMissingError,
                RefreshTokenInvalidError,
                ForbiddenError,
                TokenExpiredError,
                TokenMissingError,
            ) as refresh_exc:
                app_logger.warning(
                    f"validate_user: refresh failed with {type(refresh_exc).__name__}: {getattr(refresh_exc, 'message', str(refresh_exc))}"
                )
                return None, None
    except (TokenExpiredError, TokenMissingError, TokenInvalidError) as e:
        return None, None
    except Exception as e:
        error_logger.exception(f"Error validating user: {e}")
        return None, None


def _send_email(email_data: EmailData) -> None:
    params: resend.Emails.SendParams = {
        "from": "Tureluurtje <no-reply@iteam.kwako.nl>",
        "to": [email_data.to],
        "subject": email_data.subject,
        "html": f"{email_data.message}",
    }
    try:
        email: resend.Emails.SendResponse = resend.Emails.send(params)
        if email:
            return
        else:
            raise
    except:
        app_logger.error("Email did not send correctly")
        raise InternalError()


def send_account_verification_email_service(
    user_id: UUID, db: Optional[Session] = None
) -> None:
    user_email = _get_email_from_user_id(user_id=user_id, db=db)
    if not user_email:
        raise InternalError()

    verification_token = create_verification_token(
        user_id=user_id,
        purpose=VerificationTokenPurposes.EMAIL_VERIFICATION,
        db=db,
    )

    scheme = "https" if SECURE_COOKIES else "http"
    verification_url = f"{scheme}://{HOST}:{PORT}/api/verify?token={verification_token}"

    html_message = f"""<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist+Mono:ital,wght@0,100..900;1,100..900&family=Geist:wght@100..900&display=swap" rel="stylesheet">
<body style="display: flex; font-family: 'Geist', sans-serif;">
    <div style="margin: auto; text-align: center; width: 35%; border: 1px solid black; padding: 2rem; border-radius: 10px;">
        <h1 style="color: black;">Verify Your Email</h1>
        <p>Use the button below to verify your email. It will expire in 60 minutes.</p>
        <button style="background-color: #007bff; color: white; border: none; padding: 10px 20px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; margin: 4px 2px; cursor: pointer; border-radius: 5px;"><a href="{verification_url}" style="color: white; text-decoration: none;">Verify Email</a></button>
        <br>
        <p>If the button above does not work, copy and paste the following link into your browser:</p>
        <p style="color: blue;"><a href="{verification_url}" style="color: blue; text-decoration: none;">{verification_url}</a></p>
        <p style="color: gray; font-size: 12px;">If you did not request this email, please ignore this email.</p>
    </div>
</body>
"""

    email_data = EmailData(
        to=user_email,
        subject="Account verification",
        message=html_message,
    )
    _send_email(email_data=email_data)


def send_forgotten_password_email_service(
    user_id: UUID, db: Optional[Session] = None
) -> None:
    user_email = _get_email_from_user_id(user_id=user_id, db=db)
    if not user_email:
        raise UserNotFoundError()

    verification_token = create_verification_token(
        user_id=user_id,
        purpose=VerificationTokenPurposes.PASSWORD_RESET,
        db=db,
    )

    scheme = "https" if SECURE_COOKIES else "http"
    verification_url = f"{scheme}://{HOST}:{PORT}/api/verify?token={verification_token}"

    html_message = f"""<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist+Mono:ital,wght@0,100..900;1,100..900&family=Geist:wght@100..900&display=swap" rel="stylesheet">
<body style="display: flex; font-family: 'Geist', sans-serif;">
    <div style="margin: auto; text-align: center; width: 35%; border: 1px solid black; padding: 2rem; border-radius: 10px;">
        <h1 style="color: black;">Password Reset Request</h1>
        <p>Use the button below to reset your password. It will expire in 60 minutes.</p>
        <button style="background-color: #007bff; color: white; border: none; padding: 10px 20px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; margin: 4px 2px; cursor: pointer; border-radius: 5px;"><a href="{verification_url}" style="color: white; text-decoration: none;">Reset Password</a></button>
        <br>
        <p>If the button above does not work, copy and paste the following link into your browser:</p>
        <p style="color: blue;"><a href="{verification_url}" style="color: blue; text-decoration: none;">{verification_url}</a></p>
        <p style="color: gray; font-size: 12px;">If you did not request this email, please ignore this email.</p>
    </div>
</body>
"""

    email_data = EmailData(
        to=user_email,
        subject="Password Reset",
        message=html_message,
    )
    _send_email(email_data=email_data)


def verify_verification_token(
    token: str, token_type_to_check: Optional[VerificationTokenPurposes], db: Session
) -> VerificationTokens:
    verification_token = (
        db.query(VerificationTokens)
        .filter(
            VerificationTokens.token == hash_token(token),
            VerificationTokens.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )

    if not verification_token:
        raise VerificationTokenInvalidError()

    if (
        token_type_to_check is not None
        and verification_token.purpose != token_type_to_check
    ):
        raise VerificationTokenInvalidError()

    return verification_token


def verify_email_service(token: str) -> None:
    """Function to verify the account of an user

    Args:
        token (str): The token provided in the mail the user got to verify their account

    Raises:
        InternalError: User id not found in db for given token
    """
    with get_db_session() as db:
        verification_token = verify_verification_token(
            token=token,
            token_type_to_check=VerificationTokenPurposes.EMAIL_VERIFICATION,
            db=db,
        )

        user = db.get(User, verification_token.user_id)

        if not user:
            app_logger.error(
                msg=f"User not found for id {verification_token.user_id} from verfication tokens table"
            )
            raise InternalError()

        user.verified = True
        db.delete(verification_token)
        db.commit()


def change_password_service(
    user_id: UUID, old_password: str, new_password: str
) -> None:
    with get_db_session() as db:
        change_password(
            user_id=user_id, old_password=old_password, new_password=new_password, db=db
        )
        # Commit to the database
        db.commit()


def reset_forgotten_password_service(token: str, new_password: str):
    with get_db_session() as db:
        verification_token = verify_verification_token(
            token=token,
            token_type_to_check=VerificationTokenPurposes.PASSWORD_RESET,
            db=db,
        )

        set_password(
            user=get_user(user_id=verification_token.user_id, db=db),
            new_password=new_password,
        )
        db.delete(verification_token)
        db.commit()
