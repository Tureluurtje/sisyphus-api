from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest

from api.models.auth import User
from api.schema.http.users import UpdateUserSettings
from api.schema.internal.errors import NotImplementedYetError
from api.services import users_service


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


def test_get_user_profile():
    user = make_user()
    db = MagicMock()
    db.get.return_value = user
    db.query.return_value.where.return_value.count.return_value = 3
    with patch("api.services.users_service.get_user_review_streak", return_value=4):
        profile = users_service.get_user_profile(user.id, db)
    assert profile.user_id == user.id
    assert profile.streak == 4
    assert profile.total_words_learned == 3


def test_update_user_settings_grade():
    user = make_user()
    db = MagicMock()
    db.get.return_value = user
    settings = UpdateUserSettings(grade=7, email=None)
    with patch("api.services.users_service.get_user_review_streak", return_value=5):
        updated = users_service.update_user_settings(user.id, settings, db)
    assert updated.grade == 7
    assert updated.streak == 5


def test_update_user_settings_email_unimplemented():
    user = make_user()
    db = MagicMock()
    db.get.return_value = user
    with pytest.raises(NotImplementedYetError):
        users_service.update_user_settings(
            user.id, UpdateUserSettings(email="new@example.com"), db
        )
    assert user.grade == 6
