from types import SimpleNamespace

from fastapi import Response
from unittest.mock import MagicMock

from api.services.auth import cookies


def test_set_auth_cookies_and_clear_auth_cookies():
    response = MagicMock(spec=Response)
    cookies.set_auth_cookies(
        {"access_token": "a", "refresh_token": "r", "csrf_token": "c"}, response
    )

    assert response.set_cookie.call_count == 3
    assert response.set_cookie.call_args_list[0].kwargs["key"] == "access_token"
    assert response.set_cookie.call_args_list[2].kwargs["key"] == "csrf_token"

    response = MagicMock(spec=Response)
    cookies.clear_auth_cookies(response)
    assert response.set_cookie.call_count == 3
    assert response.set_cookie.call_args_list[0].kwargs["max_age"] == 0


def test_apply_refreshed_token_cookies_and_cookie_helpers():
    response = MagicMock(spec=Response)
    connection = SimpleNamespace(
        state=SimpleNamespace(refreshed_tokens={"access_token": "a"})
    )
    cookies.apply_refreshed_token_cookies(connection, response)

    assert response.set_cookie.called
    assert (
        cookies.get_access_token_cookie(
            SimpleNamespace(cookies={"access_token": "cookie-token"}, headers={})
        )
        == "cookie-token"
    )
    assert (
        cookies.get_refresh_token_cookie(
            SimpleNamespace(cookies={"refresh_token": "refresh-token"})
        )
        == "refresh-token"
    )


def test_header_access_token_and_csrf_validation():
    connection = SimpleNamespace(
        headers={"Authorization": "Bearer header-token"}, cookies={}, query_params={}
    )
    assert cookies._get_access_token_from_header(connection) == "header-token"

    connection = SimpleNamespace(
        headers={}, cookies={}, query_params={"token": "query-token"}
    )
    assert cookies._get_access_token_from_header(connection) == "query-token"

    assert (
        cookies.check_csrf(
            SimpleNamespace(
                cookies={"csrf_token": "abc"}, headers={"X-CSRF-Token": "abc"}
            )
        )
        is True
    )
    assert (
        cookies.check_csrf(
            SimpleNamespace(
                cookies={"csrf_token": "abc"}, headers={"X-CSRF-Token": "xyz"}
            )
        )
        is False
    )
