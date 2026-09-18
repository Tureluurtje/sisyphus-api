from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock, patch

from api.models.auth import User, VerificationTokenPurposes
from api.schema.internal.auth import AuthTokens
from api.services.auth import tokens as auth_tokens


def test_ensure_timezone_aware():
    assert auth_tokens._ensure_timezone_aware(None) is None
    assert (
        auth_tokens._ensure_timezone_aware(datetime(2024, 1, 1)).tzinfo == timezone.utc
    )


def test_get_valid_refresh_token_entry():
    db = MagicMock()
    row = SimpleNamespace(
        token=auth_tokens.hash_token("raw"),
        revoked=False,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    db.query.return_value.filter.return_value.first.return_value = row
    assert auth_tokens.get_valid_refresh_token_entry("raw", db) is row


def test_create_access_token_and_refresh_token():
    token = auth_tokens._create_access_token(uuid4())
    assert isinstance(token, str)
    assert len(token) > 10

    db = MagicMock()
    db.add.side_effect = lambda instance: setattr(instance, "id", uuid4())
    refresh = auth_tokens._create_refresh_token(uuid4(), db)
    assert isinstance(refresh.token, str)
    assert refresh.id is not None


def test_create_verification_token_and_csrf_token():
    db = MagicMock()
    db.add.side_effect = lambda instance: setattr(instance, "id", uuid4())
    user = User(
        id=uuid4(),
        username="u",
        grade=6,
        email="u@example.com",
        password="pw",
        verified=False,
    )
    db.get.return_value = user
    created = auth_tokens.create_verification_token(
        user.id, VerificationTokenPurposes.EMAIL_VERIFICATION, db
    )
    assert isinstance(created, str)
    assert len(created) > 10
    assert isinstance(auth_tokens._create_csrf_token(), str)


def test_rotate_refresh_token_and_hash_verification():
    db = MagicMock()
    old_row = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        revoked=False,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db.query.return_value.filter.return_value.first.return_value = old_row
    with patch(
        "api.services.auth.tokens._create_refresh_token",
        return_value=SimpleNamespace(token="new-token", id=uuid4()),
    ), patch("api.services.auth.tokens.revoke_refresh_token"):
        rotated = auth_tokens._rotate_refresh_token("old-token", db)
    assert rotated.token == "new-token"
    assert auth_tokens.hash_token("abc") == auth_tokens.hash_token("abc")


def test_verify_verification_token_and_verify_token():
    db = MagicMock()
    entry = SimpleNamespace(
        token=auth_tokens.hash_token("abc"),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        purpose=VerificationTokenPurposes.EMAIL_VERIFICATION,
    )
    db.query.return_value.filter.return_value.first.return_value = entry
    assert (
        auth_tokens.verify_verification_token(
            "abc", VerificationTokenPurposes.EMAIL_VERIFICATION, db
        )
        is entry
    )
    assert auth_tokens.verify_token("abc", auth_tokens.hash_token("abc")) is True


def test_validate_access_token():
    user_id = uuid4()
    jti = uuid4()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch(
        "api.services.auth.tokens.jwt.decode",
        return_value={
            "sub": str(user_id),
            "exp": int(datetime.now(timezone.utc).timestamp()) + 60,
            "jti": str(jti),
        },
    ):
        payload = auth_tokens.validate_access_token("token", db)
    assert payload.sub == user_id
    assert payload.jti == jti


def test_revoke_refresh_and_access_tokens():
    db = MagicMock()
    auth_tokens.revoke_refresh_token(uuid4(), db)
    auth_tokens.revoke_all_refresh_tokens_for_user(uuid4(), db)
    assert db.query.called

    with patch(
        "api.services.auth.tokens.validate_access_token",
        return_value=SimpleNamespace(
            sub=uuid4(),
            jti=uuid4(),
            exp=int(datetime.now(timezone.utc).timestamp()) + 60,
        ),
    ):
        auth_tokens.revoke_access_token("token", db)
    assert db.add.called


def test_issue_auth_tokens():
    with patch(
        "api.services.auth.tokens._create_access_token", return_value="access"
    ), patch(
        "api.services.auth.tokens._create_refresh_token",
        return_value=SimpleNamespace(token="refresh", id=uuid4()),
    ), patch(
        "api.services.auth.tokens._create_csrf_token", return_value="csrf"
    ):
        result = auth_tokens.issue_auth_tokens(uuid4(), MagicMock())
    assert result.access_token == "access"
    assert result.refresh_token == "refresh"
    assert result.csrf_token == "csrf"
