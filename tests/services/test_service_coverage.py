from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request, Response
from psycopg import InternalError

from api.models.auth import User, VerificationTokenPurposes
from api.schema.http.users import UpdateUserSettings
from api.schema.internal.auth import AuthTokens, EmailData
from api.schema.internal.errors import (
    AccountNotVerifiedError,
    ConflictError,
    InternalError as AppInternalError,
    InvalidInputError,
    NotImplementedYetError,
    TokenExpiredError,
    UserNotFoundError,
)
from api.schema.internal.words import LoadChapter, LoadWord, LoadWordList, ReviewedWord
from api.services import leaderboard_service, users_service, words_service
from api.services.auth import (
    accounts,
    cookies,
    dependencies,
    email,
    passwords,
    tokens as auth_tokens,
)


def make_user(**overrides):
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        username="demo-user",
        grade=6,
        email="demo@example.com",
        password="hashed-password",
        verified=True,
        dev=False,
        created_at=now,
        updated_at=now,
    )
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def test_accounts_service_functions():
    user = make_user()
    db = MagicMock()
    db.get.return_value = user

    assert accounts.user_is_verified(user.id, db) is True
    assert accounts.get_user(user.id, db) is user

    db.get.return_value = user
    with patch("api.services.auth.accounts.verify_password", return_value=True), patch(
        "api.services.auth.accounts.set_password"
    ) as set_password_mock:
        accounts.change_user_password(user.id, "old-pass", "new-pass", db)
    set_password_mock.assert_called_once_with(password="new-pass", user_object=user)

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    tokens = AuthTokens(access_token="a", refresh_token="r", csrf_token="c")
    with patch("api.services.auth.accounts.verify_password", return_value=True), patch(
        "api.services.auth.accounts.issue_auth_tokens", return_value=tokens
    ):
        assert accounts.authenticate_user(user.email, "secret", db) == tokens

    user.verified = False
    with patch("api.services.auth.accounts.verify_password", return_value=True):
        with pytest.raises(AccountNotVerifiedError):
            accounts.authenticate_user(user.email, "secret", db)

    db = MagicMock()
    with patch("api.services.auth.accounts.validate_password_strength"), patch(
        "api.services.auth.accounts.hash_password", return_value="hashed"
    ), patch(
        "api.services.auth.accounts.issue_auth_tokens", return_value=tokens
    ), patch(
        "api.services.auth.email.send_verification_email"
    ):
        result = accounts.register_user(
            "new-user", 6, "new@example.com", "StrongPass!1", db
        )
    assert result.access_token == "a"

    db = MagicMock()
    db.get.return_value = user
    accounts.delete_account(user.id, db)
    db.delete.assert_called_once_with(user)

    db = MagicMock()
    db.query.return_value.filter.return_value.distinct.return_value.all.return_value = [
        (date.today(),),
        (date.today() - timedelta(days=1),),
    ]
    assert accounts.get_user_review_streak(user.id, db) == 2

    token = SimpleNamespace(user_id=user.id)
    db = MagicMock()
    db.get.return_value = user
    with patch(
        "api.services.auth.accounts.verify_verification_token", return_value=token
    ):
        accounts.verify_email("token-value", db)
    db.delete.assert_called_once_with(token)

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
    set_password_mock.assert_called_once()

    db = MagicMock()
    db.get.return_value = None
    with pytest.raises(UserNotFoundError):
        accounts.user_is_verified(uuid4(), db)

    db = MagicMock()
    db.get.return_value = None
    with pytest.raises(UserNotFoundError):
        accounts.delete_account(uuid4(), db)


def test_cookies_service_functions():
    response = MagicMock(spec=Response)
    cookies.set_auth_cookies(
        {"access_token": "a", "refresh_token": "r", "csrf_token": "c"}, response
    )
    assert response.set_cookie.call_count == 3

    connection = SimpleNamespace(
        state=SimpleNamespace(refreshed_tokens={"access_token": "a"})
    )
    cookies.apply_refreshed_token_cookies(connection, response)
    assert response.set_cookie.call_count >= 3

    response = MagicMock(spec=Response)
    cookies.clear_auth_cookies(response)
    assert response.set_cookie.call_count == 3

    assert (
        cookies.get_access_token_cookie(
            SimpleNamespace(cookies={"access_token": "cookie-token"}, headers={})
        )
        == "cookie-token"
    )
    assert (
        cookies._get_access_token_from_header(
            SimpleNamespace(
                headers={"Authorization": "Bearer header-token"}, query_params={}
            )
        )
        == "header-token"
    )
    assert (
        cookies._get_access_token_from_header(
            SimpleNamespace(headers={}, query_params={"token": "query-token"})
        )
        == "query-token"
    )
    assert (
        cookies.get_refresh_token_cookie(
            SimpleNamespace(cookies={"refresh_token": "refresh-token"})
        )
        == "refresh-token"
    )
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


def test_dependencies_service_functions():
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = "user@example.com"
    assert dependencies.get_email_from_user_id(uuid4(), db) == "user@example.com"

    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = uuid4()
    assert dependencies.get_user_id_from_email("user@example.com", db) is not None

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

    request = SimpleNamespace(cookies={})
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
        asyncio.run(dependencies.cleanup_tokens())
    assert db.query.called

    @dependencies.typed_limit("10/minute")
    def sample(request: Request, value):
        return value + 1

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
    )
    assert sample(request, 2) == 3


def test_email_service_functions():
    email_data = EmailData(to="one@example.com", subject="hello", message="<p>hi</p>")
    with patch(
        "api.services.auth.email.resend.Emails.send", return_value={"status": "queued"}
    ):
        email._send_email(email_data)

    with pytest.raises(InternalError):
        with patch(
            "api.services.auth.email.resend.Emails.send", side_effect=Exception("boom")
        ):
            email._send_email(email_data)

    db = MagicMock()
    with patch(
        "api.services.auth.email.get_email_from_user_id", return_value="one@example.com"
    ), patch(
        "api.services.auth.email.create_verification_token", return_value="abc123"
    ), patch(
        "api.services.auth.email._send_email"
    ) as send_email_mock:
        email.send_verification_email(uuid4(), db)
    assert send_email_mock.called

    db = MagicMock()
    with patch(
        "api.services.auth.email.get_user_id_from_email", return_value=uuid4()
    ), patch(
        "api.services.auth.email.create_verification_token", return_value="reset-token"
    ), patch(
        "api.services.auth.email._send_email"
    ) as send_email_mock:
        email.send_password_reset_email("user@example.com", db)
    assert send_email_mock.called


def test_password_service_functions():
    with pytest.raises(InvalidInputError):
        passwords.validate_password_strength("h")
    assert passwords.validate_password_strength("Sup3RH@rDP@SW0Rd!!82356") is None

    hashed = passwords.hash_password("hihi")
    assert passwords.verify_password("hihi", hashed) is True
    assert passwords.verify_password("wrong", hashed) is False

    user = User(
        id=uuid4(),
        username="u",
        grade=6,
        email="u@example.com",
        password="old",
        verified=True,
    )
    with patch("api.services.auth.passwords.validate_password_strength"):
        passwords.set_password(user, "new-pass")
    assert user.password != "old"


def test_auth_tokens_service_functions():
    assert auth_tokens._ensure_timezone_aware(None) is None
    assert (
        auth_tokens._ensure_timezone_aware(datetime(2024, 1, 1)).tzinfo == timezone.utc
    )

    db = MagicMock()
    row = SimpleNamespace(
        token=auth_tokens.hash_token("raw"),
        revoked=False,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    db.query.return_value.filter.return_value.first.return_value = row
    assert auth_tokens.get_valid_refresh_token_entry("raw", db) is row

    assert isinstance(auth_tokens._create_access_token(uuid4()), str)

    db = MagicMock()
    db.add.side_effect = lambda instance: setattr(instance, "id", uuid4())
    refresh = auth_tokens._create_refresh_token(uuid4(), db)
    assert isinstance(refresh.token, str)

    db = MagicMock()
    db.add.side_effect = lambda instance: setattr(instance, "id", uuid4())
    user = SimpleNamespace(id=uuid4(), verified=False)
    db.get.return_value = user
    created = auth_tokens.create_verification_token(
        user.id, VerificationTokenPurposes.EMAIL_VERIFICATION, db
    )
    assert isinstance(created, str)
    assert isinstance(auth_tokens._create_csrf_token(), str)

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
    assert auth_tokens.verify_token("abc", auth_tokens.hash_token("abc")) is True

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

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    user_id = uuid4()
    jti = uuid4()
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

    db = MagicMock()
    auth_tokens.revoke_refresh_token(uuid4(), db)
    auth_tokens.revoke_all_refresh_tokens_for_user(uuid4(), db)
    with patch(
        "api.services.auth.tokens.validate_access_token",
        return_value=SimpleNamespace(
            sub=uuid4(),
            jti=uuid4(),
            exp=int(datetime.now(timezone.utc).timestamp()) + 60,
        ),
    ):
        auth_tokens.revoke_access_token("token", db)

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


def test_leaderboard_service_functions():
    user_id = uuid4()
    user = make_user(id=user_id, username="me")
    classmate = make_user(username="peer")

    db = MagicMock()
    db.get.return_value = user
    db.query.return_value.filter.return_value.all.return_value = [user, classmate]
    assert leaderboard_service._get_classmates(user_id, db) == [user, classmate]

    db = MagicMock()
    db.get.return_value = user
    query = MagicMock()
    query.join.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(box=2),
        SimpleNamespace(box=3),
    ]
    db.query.return_value = query
    assert leaderboard_service._calculate_user_xp(user_id, db) == 5

    with patch(
        "api.services.leaderboard_service._get_classmates",
        return_value=[user, classmate],
    ), patch("api.services.leaderboard_service._calculate_user_xp", side_effect=[5, 7]):
        result = leaderboard_service.get_class_leaderboard(user_id, MagicMock())
    assert len(result.root) == 2
    assert result.root[0].xp >= result.root[1].xp

    with patch(
        "api.services.leaderboard_service.get_class_leaderboard",
        return_value=SimpleNamespace(
            root=[SimpleNamespace(user_id=user_id, rank=1, username="me", xp=5)]
        ),
    ):
        row = leaderboard_service.get_user_leaderboard(user_id, MagicMock())
    assert row.user_id == user_id


def test_users_service_functions():
    user = make_user()
    db = MagicMock()
    db.get.return_value = user
    db.query.return_value.where.return_value.count.return_value = 3
    with patch("api.services.users_service.get_user_review_streak", return_value=4):
        profile = users_service.get_user_profile(user.id, db)
    assert profile.user_id == user.id
    assert profile.streak == 4

    settings = UpdateUserSettings(grade=7, email=None)
    with patch("api.services.users_service.get_user_review_streak", return_value=5):
        updated = users_service.update_user_settings(user.id, settings, db)
    assert updated.grade == 7

    with pytest.raises(NotImplementedYetError):
        users_service.update_user_settings(
            user.id, UpdateUserSettings(email="new@example.com"), db
        )


def test_words_service_functions():
    now = datetime.now(timezone.utc)
    assert words_service._ensure_aware(datetime(2024, 1, 1)).tzinfo is not None
    assert isinstance(words_service._tomorrow_start_local_naive(), datetime)
    assert words_service.calculate_due_date(0) is not None
    assert words_service.calculate_due_date(99) is None
    assert (
        0.05
        <= words_service.calculate_new_stability(
            SimpleNamespace(stability=0.3, last_reviewed=now - timedelta(days=2)), 1, 0
        )
        <= 1.0
    )
    assert words_service.calculate_schoolyear(datetime(2025, 8, 1)) == "25-26"

    word_list = LoadWordList(
        schoolYear="25-26",
        schoolGrade=6,
        chapters=[
            LoadChapter(
                name="chapter-1",
                words=[LoadWord(word="hola", translation="hello", targetDate=now)],
            )
        ],
    )
    db = MagicMock()
    db.get.return_value = SimpleNamespace(username="Tureluurtje")
    with patch("api.services.words_service.get_db_session") as session_factory:
        session_factory.return_value.__enter__.return_value = db
        words_service.save_wordlist_service(uuid4(), word_list)
    assert db.commit.called

    user_id = uuid4()
    db = MagicMock()
    user_query = MagicMock(
        where=MagicMock(
            return_value=MagicMock(
                scalar=MagicMock(return_value=SimpleNamespace(grade=6))
            )
        )
    )
    list_query = MagicMock(
        where=MagicMock(return_value=MagicMock(scalar=MagicMock(return_value=uuid4())))
    )
    due_query = MagicMock()
    due_query.join.return_value = due_query
    due_query.outerjoin.return_value = due_query
    due_query.where.return_value = due_query
    due_query.limit.return_value = due_query
    due_query.offset.return_value = due_query
    due_query.all.return_value = [
        SimpleNamespace(
            id=uuid4(), chapter_id=uuid4(), word="hola", translation="hello"
        )
    ]
    db.query.side_effect = [user_query, list_query, due_query]
    with patch("api.services.words_service.get_db_session") as session_factory:
        session_factory.return_value.__enter__.return_value = db
        result = words_service.get_due_words_service(user_id)
    assert result[0].word == "hola"

    db = MagicMock()
    query = MagicMock()
    query.join.return_value = query
    query.where.return_value = query
    query.all.return_value = [
        SimpleNamespace(
            id=uuid4(), chapter_id=uuid4(), word="hola", translation="hello"
        )
    ]
    db.query.side_effect = [
        query,
        MagicMock(
            where=MagicMock(
                return_value=MagicMock(
                    scalar=MagicMock(return_value=SimpleNamespace(grade=6))
                )
            )
        ),
    ]
    with patch("api.services.words_service.calculate_schoolyear", return_value="25-26"):
        result = words_service.get_difficult_words_service(user_id, db, 0.5)
    assert result[0].word == "hola"

    db = MagicMock()
    card = SimpleNamespace(user_id=user_id, word_id=uuid4(), stability=0.3)
    db.query.return_value.where.return_value.first.return_value = card
    with patch("api.services.words_service.calculate_new_stability", return_value=0.7):
        words_service.submit_difficult_word_review_service(
            user_id,
            [
                ReviewedWord(
                    wordId=card.word_id,
                    reviewedAt=now,
                    correct=1,
                    incorrect=0,
                    averageResponseTimeMs=50,
                )
            ],
            db,
        )
    assert card.stability == 0.7

    db = MagicMock()
    with patch(
        "api.services.words_service.update_card_service",
        return_value=SimpleNamespace(id=uuid4()),
    ), patch("api.services.words_service.add_review_entry"):
        with patch("api.services.words_service.get_db_session") as session_factory:
            session_factory.return_value.__enter__.return_value = db
            words_service.submit_word_review_service(
                user_id,
                [
                    ReviewedWord(
                        wordId=uuid4(),
                        reviewedAt=now,
                        correct=1,
                        incorrect=0,
                        averageResponseTimeMs=50,
                    )
                ],
            )

    db = MagicMock()
    with patch("api.services.words_service.calculate_due_date", return_value=now):
        created = words_service.add_card_service(user_id, uuid4(), now, db)
    assert created is not None

    existing = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        word_id=uuid4(),
        box=0,
        due_at=now,
        last_reviewed=now,
        stability=0.3,
    )
    db = MagicMock()
    db.query.return_value.where.return_value.first.return_value = None
    with patch(
        "api.services.words_service.add_card_service", return_value=existing
    ), patch(
        "api.services.words_service.calculate_new_stability", return_value=0.8
    ), patch(
        "api.services.words_service.calculate_due_date", return_value=now
    ):
        updated = words_service.update_card_service(
            user_id,
            ReviewedWord(
                wordId=existing.word_id,
                reviewedAt=now,
                correct=1,
                incorrect=0,
                averageResponseTimeMs=50,
            ),
            db,
        )
    assert updated is existing

    with pytest.raises(AppInternalError):
        words_service.add_review_entry(user_id, uuid4(), 2, 50, now, MagicMock())

    db = MagicMock()
    db.query.return_value.where.return_value.scalar.return_value = SimpleNamespace(
        id=user_id, grade=6
    )
    query = MagicMock()
    query.join.return_value = query
    query.where.return_value = query
    query.all.return_value = [
        (
            SimpleNamespace(box=0),
            SimpleNamespace(
                id=uuid4(), chapter_id=uuid4(), word="hola", translation="hello"
            ),
        )
    ]
    db.query.return_value = query
    with patch("api.services.words_service.get_db_session") as session_factory:
        session_factory.return_value.__enter__.return_value = db
        stack = words_service.get_stack_service(user_id, all_stacks=True)
    assert stack.wordAmount == 1

    with patch("api.services.words_service.get_db_session") as session_factory:
        session_factory.return_value.__enter__.return_value = db
        stack_single = words_service.get_stack_service(
            user_id, stack_id=0, all_stacks=False
        )
    assert stack_single.stack_id == 0
