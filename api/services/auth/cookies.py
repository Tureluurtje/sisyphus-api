from typing import Optional

from fastapi import Cookie, WebSocket
from fastapi.requests import HTTPConnection
from starlette.responses import Response

from api.config import (
    ACCESS_TOKEN_EXPIRE_SECONDS,
    REFRESH_TOKEN_EXPIRE_SECONDS,
    SECURE_COOKIES,
)
from api.schema.internal.auth import AuthTokens


def set_auth_cookies(
    tokens: AuthTokens | dict[str, str], response: Response
) -> Response:
    """
    Set auth cookies on response
    """

    # Normalise token access for model or mapping
    def _get(key: str):
        if hasattr(tokens, key):
            return getattr(tokens, key)
        if isinstance(tokens, dict):
            return tokens.get(key)
        return None

    csrf_token = _get("csrf_token")
    access_token = _get("access_token")
    refresh_token = _get("refresh_token")

    if access_token is not None:
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=SECURE_COOKIES,
            samesite="none",
            max_age=int(ACCESS_TOKEN_EXPIRE_SECONDS),
            path="/",
        )

    if refresh_token is not None:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=SECURE_COOKIES,
            samesite="none",
            max_age=int(REFRESH_TOKEN_EXPIRE_SECONDS),
            path="/",
        )

    if csrf_token is not None:
        response.set_cookie( # NOSONAR python:S3330 - CSRF token must be JS-readable (double-submit pattern)
            key="csrf_token",
            value=csrf_token,
            httponly=False,
            secure=SECURE_COOKIES,
            samesite="none",
            max_age=int(REFRESH_TOKEN_EXPIRE_SECONDS),
            path="/",
        )

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
        set_auth_cookies(response=response, tokens=tokens)
    return response


def clear_auth_cookies(response: Response) -> None:
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

    response.set_cookie( # NOSONAR python:S3330 - CSRF token must be JS-readable (double-submit pattern)
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
    """
    Dependency to retrieve the access token injected by FastAPI in the connection object
    """
    # First check if the cookie is auto injected by Fastapi
    if isinstance(access_token, str) and access_token:
        return access_token

    # Then check if its in the connection object
    cookie_token = connection.cookies.get("access_token")
    if cookie_token:
        return cookie_token

    # Fallback to header bearer token for websockets
    if isinstance(connection, WebSocket):
        return _get_access_token_from_header(connection)

    return None

def _get_access_token_from_header(
    connection: HTTPConnection
) -> Optional[str]:
    # Fix: Websockets DO send cookies
    """
    Because Websockets can't sent cookies with the request, try to take access token from Bearer token from the Authorization header. If that still doesn't work try query params
    """
    auth_header = connection.headers.get("Authorization")
    # Try Bearer token
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]

    # Try query params
    token = connection.query_params.get("token")
    if token:
        return token

    return None

def get_refresh_token_cookie(
    connection: HTTPConnection, refresh_token: Optional[str] = Cookie(default=None)
) -> Optional[str]:
    # If not auto injected
    if not isinstance(refresh_token, str):
        return connection.cookies.get("refresh_token")
    # Return auto injected refresh token or None if it was not found
    return refresh_token

def check_csrf(connection: HTTPConnection) -> bool:
    try:
        return connection.cookies.get("csrf_token") == connection.headers.get(
            "X-CSRF-Token"
        )
    except AttributeError:
        return False
