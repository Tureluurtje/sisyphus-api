from fastapi import APIRouter, status, Depends, Request, Response
from uuid import UUID
import asyncio
from typing import Any, Callable, Optional, ParamSpec, TypeVar, cast

from api.schema.internal.errors import TokenInvalidError, TokenMissingError
from api.schema.internal.users import UserProfileDetail

from api.limiter import limiter

P = ParamSpec("P")
R = TypeVar("R")
_untyped_limit = getattr(limiter, "limit")


def typed_limit(
    *args: Any, **kwargs: Any
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Typed wrapper around slowapi's untyped limiter decorator."""
    return cast(
        Callable[[Callable[P, R]], Callable[P, R]], _untyped_limit(*args, **kwargs)
    )


from api.schema.http.auth import (
    LoginRequest,
    LoginResponse,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    ValidateResponse,
    LogoutResponse,
)
from api.services.auth_service import (
    authenticate_user,
    clear_token_cookies_service,
    create_tokens_service,
    get_user_data_service,
    get_user_id_from_refresh,
    register_user,
    validate_access_token,
    get_user_id,
    revoke_refresh_token,
    revoke_access_token,
    cleanup_tokens,
    get_access_token_cookie,
    response_cookies_generator,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
@typed_limit("60/minute")
def get_current_user(
    request: Request, user_id: Optional[UUID] = Depends(get_user_id)
) -> UserProfileDetail:
    if not user_id:
        raise TokenInvalidError()
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
    refresh_data: tuple[UUID, str] = Depends(get_user_id_from_refresh),
) -> RefreshResponse:
    user_id, old_refresh_token = refresh_data
    tokens = create_tokens_service(user_id=user_id, old_refresh_token=old_refresh_token)
    response_cookies_generator(response=response, tokens=tokens)
    return RefreshResponse(tokens=tokens)


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
