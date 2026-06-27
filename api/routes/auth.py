from fastapi import APIRouter, status, Depends, Request, Response
from uuid import UUID
import asyncio
from typing import Any, Callable, Optional, ParamSpec, TypeVar, cast

from api.schema.internal.errors import (
    RefreshTokenMissingError,
    TokenInvalidError,
    TokenMissingError,
)
from api.schema.internal.users import UserProfileDetail

from api.limiter import limiter

from functools import wraps
from typing import Any, Callable, ParamSpec, TypeVar, cast

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


from api.schema.http.auth import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    DeleteResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    ResetForgottenPasswordRequest,
    ResetForgottenPasswordResponse,
    ValidateResponse,
    LogoutResponse,
    VerifyEmailResponse,
)
from api.services.auth_service import (
    authenticate_user,
    change_password_service,
    clear_token_cookies_service,
    create_tokens_service,
    delete_account_service,
    get_user_data_service,
    get_user_id_from_refresh,
    get_user_id_from_refresh_body,
    get_user_id_skip_csrf,
    register_user,
    reset_forgotten_password_service,
    validate_access_token,
    get_user_id,
    revoke_refresh_token,
    revoke_access_token,
    cleanup_tokens,
    get_access_token_cookie,
    response_cookies_generator,
    verify_email_service,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
@typed_limit("60/minute")
def get_current_user(
    request: Request, user_id: UUID = Depends(get_user_id_skip_csrf)
) -> UserProfileDetail:
    return get_user_data_service(user_id=user_id)


@router.post(path="/login", status_code=status.HTTP_200_OK)
@typed_limit("10/minute")  # 10/minute per ip
async def login(
    request: Request, response: Response, data: LoginRequest
) -> LoginResponse:
    tokens = authenticate_user(email=data.email, password=data.password)
    response_cookies_generator(response=response, tokens=tokens)
    return LoginResponse(tokens=tokens)


@router.post(path="/register", status_code=status.HTTP_200_OK)
@typed_limit("10/minute")
async def register(
    request: Request, response: Response, data: RegisterRequest
) -> RegisterResponse:
    tokens = register_user(
        username=data.username,
        grade=data.grade,
        email=data.email,
        password=data.password,
    )
    response_cookies_generator(response=response, tokens=tokens)
    return RegisterResponse(tokens=tokens)


@router.get(path="/validate")
@typed_limit("60/minute")
async def validate(
    request: Request, access_token: Optional[str] = Depends(get_access_token_cookie)
) -> ValidateResponse:
    if not access_token:
        raise TokenMissingError()

    payload = validate_access_token(access_token)
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
) -> RefreshResponse:
    if cookie_data:
        user_id, old_refresh_token = cookie_data
    else:
        if body_data and body_data.old_refresh_token:
            old_refresh_token = body_data.old_refresh_token
            user_id = get_user_id_from_refresh_body(old_refresh_token)
        else:
            raise RefreshTokenMissingError()

    tokens = create_tokens_service(user_id=user_id, old_refresh_token=old_refresh_token)
    response_cookies_generator(response=response, tokens=tokens)
    return RefreshResponse(tokens=tokens)


@router.post("/verify-account")
@typed_limit("5/minute")
def verify_email(request: Request, token: str) -> VerifyEmailResponse:
    verify_email_service(
        token=token
    )  # Raises on invalid token
    return VerifyEmailResponse(success=True)


@router.patch("/reset-forgotten-password")
@typed_limit("3/minute")
def reset_forgotten_password(
    request: Request,
    data: ResetForgottenPasswordRequest,
    token: str
) -> ResetForgottenPasswordResponse:
    reset_forgotten_password_service(
        token=token,
        new_password=data.new_password
    ) # Raises on invalid token
    return ResetForgottenPasswordResponse(success=True)

@router.patch("/change-password")
@typed_limit("3/minute")
def change_password(
    request: Request,
    data: ChangePasswordRequest,
    user_id: UUID = Depends(get_user_id)
) -> ChangePasswordResponse:
    change_password_service(
        user_id=user_id,
        old_password=data.old_password,
        new_password=data.new_password
    ) # Raises on invalid token
    return ChangePasswordResponse(success=True)

@router.post(path="/logout", status_code=status.HTTP_200_OK)
@typed_limit("10/minute")
async def logout(
    request: Request,
    response: Response,
    user_id: UUID = Depends(dependency=get_user_id),
    access_token: Optional[str] = Depends(get_access_token_cookie),
) -> LogoutResponse:
    # Revoke any active refresh tokens for this user
    revoke_refresh_token(user_id=user_id)

    if access_token is not None:
        revoke_access_token(access_token)
    asyncio.create_task(coro=cleanup_tokens())  # Run cleanup before the request

    clear_token_cookies_service(response)
    return LogoutResponse(success=True)


@router.delete(path="/delete", status_code=status.HTTP_200_OK)
async def delete(
    request: Request, response: Response, user_id: UUID = Depends(get_user_id)
) -> DeleteResponse:
    delete_account_service(user_id=user_id)
    return DeleteResponse(success=True)
