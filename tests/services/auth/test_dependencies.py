from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock, patch

from fastapi import Request

from api.schema.internal.auth import AuthTokens
from api.schema.internal.errors import TokenExpiredError
from api.services.auth import dependencies


def test_get_email_and_user_id_helpers():
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = "user@example.com"
    assert dependencies.get_email_from_user_id(uuid4(), db) == "user@example.com"

    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = uuid4()
    assert dependencies.get_user_id_from_email("user@example.com", db) is not None


def test_get_user_id_and_refresh_helpers():
    user_id = uuid4()
    connection = SimpleNamespace(cookies={"access_token": "token"})
    with patch("api.services.auth.dependencies.check_csrf", return_value=True), patch(
        "api.services.auth.dependencies.get_access_token_cookie", return_value="token"
    ), patch(
        "api.services.auth.dependencies.validate_access_token",
        return_value=SimpleNamespace(sub=user_id),
    ), patch(
        "api.services.auth.dependencies.get_db_session"
    ) as session_factory, patch(
        "api.services.auth.accounts.user_is_verified", return_value=True
    ):
        session_factory.return_value.__enter__.return_value = MagicMock()
        assert dependencies.get_user_id(connection) == user_id

    with patch("api.services.auth.dependencies.get_user_id", return_value=user_id):
        assert dependencies.get_user_id_skip_csrf(connection) == user_id

    with patch(
        "api.services.auth.dependencies.get_valid_refresh_token_entry",
        return_value=SimpleNamespace(user_id=user_id),
    ):
        assert dependencies.get_user_id_from_refresh(
            SimpleNamespace(cookies={"refresh_token": "raw"}), skip_csrf=True
        ) == (user_id, "raw")
    with patch(
        "api.services.auth.dependencies.get_valid_refresh_token_entry",
        return_value=SimpleNamespace(user_id=user_id),
    ):
        assert dependencies.get_user_id_from_refresh_body("raw") == user_id


def test_validate_user_and_cleanup_tokens_and_limit():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
    )
    user_id = uuid4()
    tokens = AuthTokens(access_token="a", refresh_token="r", csrf_token="c")
    with patch(
        "api.services.auth.dependencies.validate_access_token",
        side_effect=TokenExpiredError(),
    ), patch(
        "api.services.auth.dependencies.get_user_id_from_refresh",
        return_value=(user_id, "raw"),
    ), patch(
        "api.services.auth.dependencies.issue_auth_tokens", return_value=tokens
    ):
        assert dependencies.validate_user(request, MagicMock(), allow_refresh=True) == (
            user_id,
            tokens,
        )

    db = MagicMock()
    with patch("api.services.auth.dependencies.get_db_session") as session_factory:
        session_factory.return_value.__enter__.return_value = db
        import asyncio

        asyncio.run(dependencies.cleanup_tokens())
    assert db.query.called

    @dependencies.typed_limit("10/minute")
    def sample(request: Request, value):
        return value + 1

    assert sample(request, 2) == 3
