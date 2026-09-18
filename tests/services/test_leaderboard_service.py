from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock, patch

from api.models.auth import User
from api.services import leaderboard_service


def test_get_classmates():
    user_id = uuid4()
    user = User(
        id=user_id,
        username="me",
        grade=6,
        email="me@example.com",
        password="pw",
        verified=True,
        dev=False,
    )
    classmate = User(
        id=uuid4(),
        username="peer",
        grade=6,
        email="peer@example.com",
        password="pw",
        verified=True,
        dev=False,
    )

    db = MagicMock()
    db.get.return_value = user
    db.query.return_value.filter.return_value.all.return_value = [user, classmate]
    assert leaderboard_service._get_classmates(user_id, db) == [user, classmate]
    assert len(leaderboard_service._get_classmates(user_id, db)) == 2


def test_calculate_user_xp():
    user_id = uuid4()
    user = User(
        id=user_id,
        username="me",
        grade=6,
        email="me@example.com",
        password="pw",
        verified=True,
        dev=False,
    )
    db = MagicMock()
    db.get.return_value = user
    query = MagicMock()
    query.join.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(box=2),
        SimpleNamespace(box=3),
    ]
    db.query.return_value = query
    assert leaderboard_service._calculate_user_xp(user_id, db) == 5
    assert leaderboard_service._calculate_user_xp(user_id, db) >= 0


def test_get_class_leaderboard():
    user_id = uuid4()
    user = User(
        id=user_id,
        username="me",
        grade=6,
        email="me@example.com",
        password="pw",
        verified=True,
        dev=False,
    )
    classmate = User(
        id=uuid4(),
        username="peer",
        grade=6,
        email="peer@example.com",
        password="pw",
        verified=True,
        dev=False,
    )
    with patch(
        "api.services.leaderboard_service._get_classmates",
        return_value=[user, classmate],
    ), patch("api.services.leaderboard_service._calculate_user_xp", side_effect=[5, 7]):
        result = leaderboard_service.get_class_leaderboard(user_id, MagicMock())
    assert len(result.root) == 2
    assert result.root[0].xp >= result.root[1].xp


def test_get_user_leaderboard():
    user_id = uuid4()
    with patch(
        "api.services.leaderboard_service.get_class_leaderboard",
        return_value=SimpleNamespace(
            root=[SimpleNamespace(user_id=user_id, rank=1, username="me", xp=5)]
        ),
    ):
        row = leaderboard_service.get_user_leaderboard(user_id, MagicMock())
    assert row.user_id == user_id
    assert row.rank == 1
