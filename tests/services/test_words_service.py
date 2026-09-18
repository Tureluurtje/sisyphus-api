from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest

from api.schema.internal.errors import InternalError
from api.schema.internal.words import LoadChapter, LoadWord, LoadWordList, ReviewedWord
from api.services import words_service


def test_ensure_aware_and_tomorrow_start_local_naive():
    assert words_service._ensure_aware(datetime(2024, 1, 1)).tzinfo is not None # type: ignore
    assert isinstance(words_service._tomorrow_start_local_naive(), datetime) # type: ignore
    assert words_service._tomorrow_start_local_naive().tzinfo is None # type: ignore


def test_calculate_due_date_and_new_stability():
    assert words_service.calculate_due_date(0) is not None
    assert words_service.calculate_due_date(99) is None
    card = SimpleNamespace(
        stability=0.3, last_reviewed=datetime.now(timezone.utc) - timedelta(days=2)
    )
    value = words_service.calculate_new_stability(card, 1, 0) # type: ignore
    assert 0.05 <= value <= 1.0


def test_calculate_schoolyear_and_save_wordlist_service():
    assert words_service.calculate_schoolyear(datetime(2025, 8, 1)) == "25-26"
    word_list = LoadWordList(
        schoolYear="25-26",
        schoolGrade=6,
        chapters=[
            LoadChapter(
                name="chapter-1",
                words=[
                    LoadWord(
                        word="hola",
                        translation="hello",
                        targetDate=datetime.now(timezone.utc),
                    )
                ],
            )
        ],
    )
    db = MagicMock()
    db.get.return_value = SimpleNamespace(username="Tureluurtje")
    with patch("api.services.words_service.get_db_session") as session_factory:
        session_factory.return_value.__enter__.return_value = db
        words_service.save_wordlist_service(uuid4(), word_list)
    assert db.commit.called
    assert db.flush.called


def test_get_due_words_service():
    user_id = uuid4()
    db = MagicMock()
    query = MagicMock()
    query.join.return_value = query
    query.outerjoin.return_value = query
    query.where.return_value = query
    query.limit.return_value = query
    query.offset.return_value = query
    query.all.return_value = [
        SimpleNamespace(
            id=uuid4(), chapter_id=uuid4(), word="hola", translation="hello"
        )
    ]
    db.query.side_effect = [
        MagicMock(
            where=MagicMock(
                return_value=MagicMock(
                    scalar=MagicMock(return_value=SimpleNamespace(grade=6))
                )
            )
        ),
        MagicMock(
            where=MagicMock(
                return_value=MagicMock(scalar=MagicMock(return_value=uuid4()))
            )
        ),
        query,
    ]
    with patch("api.services.words_service.get_db_session") as session_factory:
        session_factory.return_value.__enter__.return_value = db
        result = words_service.get_due_words_service(user_id)
    assert result is not None
    assert result[0].word == "hola"


def test_get_difficult_words_service():
    user_id = uuid4()
    db = MagicMock()
    user_query = MagicMock()
    user_query.where.return_value.scalar.return_value = SimpleNamespace(grade=6)

    word_query = MagicMock()
    word_query.join.return_value = word_query
    word_query.where.return_value = word_query
    word_query.all.return_value = [
        SimpleNamespace(
            id=uuid4(), chapter_id=uuid4(), word="hola", translation="hello"
        )
    ]

    db.query.side_effect = [word_query, user_query]
    with patch("api.services.words_service.calculate_schoolyear", return_value="25-26"):
        result = words_service.get_difficult_words_service(user_id, db, 0.5)
    assert result[0].word == "hola" # type: ignore
    assert result[0].translation == "hello" # type: ignore


def test_submit_difficult_word_review_service():
    user_id = uuid4()
    now = datetime.now(timezone.utc)
    card = SimpleNamespace(user_id=user_id, word_id=uuid4(), stability=0.3)
    db = MagicMock()
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
    assert db.flush.called


def test_submit_word_review_service():
    user_id = uuid4()
    now = datetime.now(timezone.utc)
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
    assert db.commit.called


def test_add_card_service_and_update_card_service():
    user_id = uuid4()
    now = datetime.now(timezone.utc)
    db = MagicMock()
    with patch("api.services.words_service.calculate_due_date", return_value=now):
        created = words_service.add_card_service(user_id, uuid4(), now, db)
    assert created is not None
    assert db.flush.called

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
    assert updated.stability == 0.8


def test_add_review_entry_and_get_stack_service():
    with pytest.raises(InternalError):
        words_service.add_review_entry(
            uuid4(), uuid4(), 2, 50, datetime.now(timezone.utc), MagicMock()
        )

    db = MagicMock()
    db.query.return_value.where.return_value.scalar.return_value = SimpleNamespace(
        id=uuid4(), grade=6
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
        stack = words_service.get_stack_service(uuid4(), all_stacks=True)
    assert stack.wordAmount == 1

    with patch("api.services.words_service.get_db_session") as session_factory:
        session_factory.return_value.__enter__.return_value = db
        stack_single = words_service.get_stack_service(
            uuid4(), stack_id=0, all_stacks=False
        )
    assert stack_single.stack_id == 0 # type: ignore
    assert stack_single.wordAmount == 1
