from pathlib import Path

from fastapi import APIRouter, status, Depends, Request, Response
from uuid import UUID
import asyncio
from typing import Optional

from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from api.schema.internal.auth import AuthTokens
from api.services.auth.oauth import apple_callback_handler, google_callback_handler, initiate_google_oauth
from sqlalchemy.orm import Session as DbSession

from api.database import get_db_session_dependency
from api.routes.users import get_current_user
from api.schema.internal.errors import (
    BadRequestError,
    RefreshTokenMissingError,
    TokenInvalidError,
    TokenMissingError,
    UserNotFoundError,
)

from api.schema.internal.users import UserProfileDetail
from api.services.auth.accounts import (
    authenticate_user,
    change_user_password,
    delete_account,
    register_user,
    reset_password,
    user_is_verified,
    verify_email,
)
from api.services.auth.cookies import (
    clear_auth_cookies,
    get_access_token_cookie,
    set_auth_cookies,
)
from api.services.auth.dependencies import (
    cleanup_tokens,
    get_user_id,
    get_user_id_from_email,
    get_user_id_from_refresh,
    get_user_id_from_refresh_body,
    typed_limit,
)
from api.services.auth.email import send_password_reset_email, send_verification_email
from api.services.auth.oauth import initiate_google_oauth
from api.services.auth.tokens import (
    issue_auth_tokens,
    revoke_access_token,
    revoke_all_refresh_tokens_for_user,
    validate_access_token,
)


from api.schema.http.auth import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    DeleteResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    RequestAccountVerificationEmail,
    ResetForgottenPasswordRequest,
    ResetForgottenPasswordResponse,
    SendForgottenPasswordEmailResponse,
    ValidateResponse,
    LogoutResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(path="/login", status_code=status.HTTP_200_OK)
@typed_limit("10/minute")  # 10/minute per ip
async def login(
    request: Request,
    response: Response,
    data: LoginRequest,
    db: DbSession = Depends(get_db_session_dependency),
) -> LoginResponse:
    tokens = authenticate_user(email=data.email, password=data.password, db=db)
    db.commit()
    set_auth_cookies(response=response, tokens=tokens)
    return LoginResponse(tokens=tokens)


@router.post(path="/register", status_code=status.HTTP_200_OK)
@typed_limit("10/minute")
async def register(
    request: Request,
    response: Response,
    data: RegisterRequest,
    db: DbSession = Depends(get_db_session_dependency),
) -> None:
    tokens = register_user(
        username=data.username,
        grade=data.grade,
        email=data.email,
        password=data.password,
        db=db,
    )
    db.commit()
    set_auth_cookies(response=response, tokens=tokens)
    return None

@router.get(path="/me")
@typed_limit("60/minute")
async def me_wrapper(request: Request, user_id: UUID = Depends(get_user_id), db: DbSession = Depends(get_db_session_dependency)) -> UserProfileDetail:
    return get_current_user(request, user_id, db)

@router.get(path="/validate")
@typed_limit("60/minute")
async def validate(
    request: Request,
    access_token: Optional[str] = Depends(get_access_token_cookie),
    db: DbSession = Depends(get_db_session_dependency),
) -> ValidateResponse:
    if not access_token:
        raise TokenMissingError()

    payload = validate_access_token(access_token, db=db)
    if not payload:
        raise TokenInvalidError()

    return ValidateResponse(active=True, payload=payload)


@router.post(path="/refresh", status_code=status.HTTP_200_OK)
@typed_limit("5/minute")
async def refresh(
    request: Request,
    response: Response,
    body_data: Optional[RefreshRequest] = None,
    cookie_data: Optional[tuple[UUID, str]] = Depends(get_user_id_from_refresh),
    db: DbSession = Depends(get_db_session_dependency),
) -> RefreshResponse:
    if cookie_data:
        user_id, old_refresh_token = cookie_data
    else:
        if body_data and body_data.old_refresh_token:
            old_refresh_token = body_data.old_refresh_token
            user_id = get_user_id_from_refresh_body(old_refresh_token)
        else:
            raise RefreshTokenMissingError()

    tokens = issue_auth_tokens(
        user_id=user_id, old_refresh_token=old_refresh_token, db=db
    )
    db.commit()
    set_auth_cookies(response=response, tokens=tokens)
    return RefreshResponse(tokens=tokens)


@router.get("/request-account-verification-email")
@typed_limit("1/minute")
def request_account_verification_email(
    request: Request, email: str, db: DbSession = Depends(get_db_session_dependency)
) -> RequestAccountVerificationEmail:
    user_id = get_user_id_from_email(email=email, db=db)
    if not user_id:
        raise UserNotFoundError()
    if user_is_verified(user_id=user_id, db=db):
        raise BadRequestError("The user is already verified")
    send_verification_email(user_id=user_id, db=db)
    db.commit()
    return RequestAccountVerificationEmail(success=True)


# Use get so browser can call
@router.get("/verify-account")
@typed_limit("5/minute")
def verify_account(
    request: Request, token: str, db: DbSession = Depends(get_db_session_dependency)
) -> RedirectResponse:
    verify_email(token=token, db=db)  # Raises on invalid token
    return RedirectResponse(
        url="https://sisyphus.kwako.nl/email-verified", status_code=303
    )


@router.post("/send-forgotten-password-email")
@typed_limit("3/minute")
def send_forgotten_password_email(
    request: Request, email: str, db: DbSession = Depends(get_db_session_dependency)
) -> SendForgottenPasswordEmailResponse:
    send_password_reset_email(email=email, db=db)
    db.commit()

    return SendForgottenPasswordEmailResponse(success=True)


@router.get("/reset-forgotten-password")
@typed_limit("60/minute")
def reset_forgotten_password_get(request: Request, token: str):
    try:
        return FileResponse(
            path=str(Path(__file__).parents[1] / "public" / "reset-password.html")
        )
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Not found"})


@router.patch("/reset-forgotten-password")
@typed_limit("3/minute")
def reset_forgotten_password_patch(
    request: Request,
    data: ResetForgottenPasswordRequest,
    token: str,
    db: DbSession = Depends(get_db_session_dependency),
) -> ResetForgottenPasswordResponse:
    reset_password(
        token=token, new_password=data.new_password, db=db
    )  # Raises on invalid token
    db.commit()
    return ResetForgottenPasswordResponse(success=True)


@router.patch("/change-password")
@typed_limit("3/minute")
def change_password(
    request: Request,
    data: ChangePasswordRequest,
    user_id: UUID = Depends(get_user_id),
    db: DbSession = Depends(get_db_session_dependency),
) -> ChangePasswordResponse:
    change_user_password(
        user_id=user_id,
        old_password=data.old_password,
        new_password=data.new_password,
        db=db,
    )
    db.commit()
    return ChangePasswordResponse(success=True)


@router.post(path="/logout", status_code=status.HTTP_200_OK)
@typed_limit("10/minute")
async def logout(
    request: Request,
    response: Response,
    user_id: UUID = Depends(dependency=get_user_id),
    access_token: Optional[str] = Depends(get_access_token_cookie),
    db: DbSession = Depends(get_db_session_dependency),
) -> LogoutResponse:
    # Revoke any active refresh tokens for this user
    revoke_all_refresh_tokens_for_user(user_id=user_id, db=db)

    if access_token is not None:
        revoke_access_token(access_token, db=db)
    db.commit()

    asyncio.create_task(coro=cleanup_tokens())  # Run cleanup before the request

    clear_auth_cookies(response)
    return LogoutResponse(success=True)


@router.delete(path="/delete", status_code=status.HTTP_200_OK)
async def delete(
    request: Request,
    response: Response,
    user_id: UUID = Depends(get_user_id),
    db: DbSession = Depends(get_db_session_dependency),
) -> DeleteResponse:
    delete_account(user_id=user_id, db=db)
    db.commit()
    return DeleteResponse(success=True)

# Google

@router.get("/google")
def google_login(request: Request) -> RedirectResponse:
    authorization_url, state, code_verifier = initiate_google_oauth()

    request.session["google_state"] = state
    request.session["google_code_verifier"] = code_verifier

    return RedirectResponse(url=authorization_url)


@router.get("/google/callback")
def google_callback(request: Request, db: DbSession = Depends(get_db_session_dependency)) -> AuthTokens:
    tokens = google_callback_handler(request, db)
    db.commit()
    return tokens

@router.post("/apple/callback")
def apple_callback(data: AppleCallBackRequest, request: Request, db: DbSession = Depends(get_db_session_dependency)):
    return apple_callback_handler(
        identity_token=data.identity_token,
        client_id=settings.APPLE_CLIENT_ID,
        nonce=data.nonce,
        db=db,
    )
