from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from api.models.auth import User
from api.schema.internal.auth import AuthTokens
from api.schema.internal.errors import (
    AccountNotVerifiedError,
    ConflictError,
    InvalidCredentialsError,
    InvalidInputError,
    UserNotFoundError,
)
from api.services.auth import accounts


def make_user(**overrides):
    user = User(
        id=uuid4(),
        username="demo-user",
        grade=6,
        email="demo@example.com",
        password="hashed-password",
        verified=True,
        dev=False,
    )
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def test_user_is_verified_and_get_user():
    user = make_user()
    db = MagicMock()
    db.get.return_value = user

    assert accounts.user_is_verified(user.id, db) is True
    assert accounts.get_user(user.id, db) is user

    db.get.return_value = None
    with pytest.raises(UserNotFoundError):
        accounts.user_is_verified(uuid4(), db)


def test_change_password_and_authenticate():
    user = make_user()
    db = MagicMock()
    db.get.return_value = user

    with patch("api.services.auth.accounts.verify_password", return_value=True), patch(
        "api.services.auth.accounts.set_password"
    ) as set_password_mock:
        accounts.change_user_password(user.id, "old-pass", "new-pass", db)

    assert set_password_mock.call_count == 1
    assert user.id == db.get.return_value.id

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    tokens = AuthTokens(access_token="a", refresh_token="r", csrf_token="c")
    with patch("api.services.auth.accounts.verify_password", return_value=True), patch(
        "api.services.auth.accounts.issue_auth_tokens", return_value=tokens
    ):
        result = accounts.authenticate_user(user.email, "secret", db)
    assert result == tokens

    user.verified = False
    with patch("api.services.auth.accounts.verify_password", return_value=True):
        with pytest.raises(AccountNotVerifiedError):
            accounts.authenticate_user(user.email, "secret", db)


def test_register_delete_and_review_streak():
    db = MagicMock()
    with patch("api.services.auth.accounts.validate_password_strength"), patch(
        "api.services.auth.accounts.hash_password", return_value="hashed"
    ), patch(
        "api.services.auth.accounts.issue_auth_tokens",
        return_value=AuthTokens(access_token="a", refresh_token="b", csrf_token="c"),
    ), patch(
        "api.services.auth.email.send_verification_email"
    ):
        result = accounts.register_user(
            "new-user", 6, "new@example.com", "StrongPass!1", db
        )
    assert result.access_token == "a"
    assert result.refresh_token == "b"

    db.flush.side_effect = IntegrityError(
        "INSERT INTO users", "params", "duplicate username"
    )
    with patch("api.services.auth.accounts.validate_password_strength"), patch(
        "api.services.auth.accounts.hash_password", return_value="hashed"
    ):
        with pytest.raises(ConflictError):
            accounts.register_user("new-user", 6, "new@example.com", "StrongPass!1", db)

    user = make_user()
    db = MagicMock()
    db.get.return_value = user
    accounts.delete_account(user.id, db)
    assert db.delete.called

    db = MagicMock()
    db.query.return_value.filter.return_value.distinct.return_value.all.return_value = [
        (date.today(),),
        (date.today() - timedelta(days=1),),
    ]
    assert accounts.get_user_review_streak(user.id, db) == 2


def test_verify_email_and_reset_password():
    user = make_user(verified=False)
    db = MagicMock()
    db.get.return_value = user
    token = SimpleNamespace(user_id=user.id)

    with patch(
        "api.services.auth.accounts.verify_verification_token", return_value=token
    ):
        accounts.verify_email("token-value", db)
    assert db.delete.called

    db = MagicMock()
    db.get.return_value = user
    with patch(
        "api.services.auth.accounts.verify_verification_token", return_value=token
    ), patch("api.services.auth.accounts.verify_password", return_value=True):
        with pytest.raises(InvalidInputError):
            accounts.reset_password("token-value", "old-pass", db)

    with patch(
        "api.services.auth.accounts.verify_verification_token", return_value=token
    ), patch("api.services.auth.accounts.verify_password", return_value=False), patch(
        "api.services.auth.accounts.set_password"
    ) as set_password_mock:
        accounts.reset_password("token-value", "new-pass", db)
    assert set_password_mock.called
    assert db.delete.called
