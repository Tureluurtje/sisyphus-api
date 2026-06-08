from uuid import UUID
from datetime import datetime, timedelta, timezone
from typing import Optional

from api.schema.internal.words import ReviewedWord, LoadWordList
from api.models.words import Cards, Chapters, Lists, Words
from api.models.auth import User
from api.database import get_db_session
from api.logging_config import app_logger
from api.schema.internal.errors import NotFoundError, InternalError


def calculate_due_date(box: int) -> Optional[datetime]:
    now = datetime.now()
    match box:
        case 0:
            return now
        case 1:
            next_day = now + timedelta(days=1)
            while next_day.weekday() >= 5:
                next_day += timedelta(days=1)
            return next_day
        case 2:
            for days_ahead in range(1, 8):
                candidate = now + timedelta(days=days_ahead)
                if candidate.weekday() in (1, 4):
                    return candidate
            return now
        case 3:
            days_ahead = (6 - now.weekday()) % 7 or 7
            return now + timedelta(days=days_ahead)
        case 4:
            days_ahead = (7 - now.weekday()) % 7
            days_ahead = 14 if days_ahead == 0 else days_ahead + 7
            return now + timedelta(days=days_ahead)
        case 5:
            year = now.year + (1 if now.month == 12 else 0)
            month = 1 if now.month == 12 else now.month + 1
            day = (
                min(
                    now.day, (datetime(year, month % 12 + 1, 1) - timedelta(days=1)).day
                )
                if month != 12
                else min(now.day, 31)
            )
            return now.replace(year=year, month=month, day=day)
        case _:
            app_logger.warning(f"box number of {box} not in allowed numbers(0-5)")
            return None


def calculate_new_stability(
    card: Cards,
    correct_count: int,
    incorrect_count: int,
) -> float:
    stability = card.stability or 0.3

    # success ratio
    total = correct_count + incorrect_count
    accuracy = correct_count / max(total, 1)

    # days since review
    days_since_review = (datetime.now(timezone.utc) - card.last_reviewed).days

    if days_since_review < 1:
        days_since_review = 1

    # growth from successful recalls
    growth = 0.05 * accuracy * min(days_since_review, 30)

    # penalty from mistakes
    penalty = 0.08 * (1 - accuracy)

    new_stability = stability + growth - penalty

    return max(0.05, min(1.0, new_stability))


def save_wordlist_service(user_id: UUID, word_list: LoadWordList) -> None:
    # TODO: Check if user has admin priveleges

    with get_db_session() as db:
        # First add List
        new_list = Lists(
            schoolyear=word_list.schoolYear,
            schoolgrade=word_list.schoolGrade,
        )

        db.add(new_list)
        db.flush()

        new_list_id = new_list.id

        for chapter in word_list.chapters:
            new_chapter = Chapters(list_id=new_list_id, name=chapter.name)
            db.add(new_chapter)
            db.flush()

            new_chapter_id = new_chapter.id

            for word in chapter.words:
                new_word = Words(
                    chapter_id=new_chapter_id,
                    word=word.word,
                    translation=word.translation,
                    target_date=word.targetDate
                )
                db.add(new_word)

        db.commit()
        return



def get_due_words_service(user_id: UUID):
    with get_db_session() as db:
        # First query for current year
        learnyear = db.query(User.grade).where(User.id == user_id).scalar()

        if not learnyear:
            app_logger.error(f"Grade not found for user with id {user_id}")

        # Then find cards for this year
        ...


def add_card_service(user_id: UUID, word_id: UUID) -> Cards:
    with get_db_session() as db:
        new_card = Cards(user_id=user_id, word_id=word_id, box=0)
        db.add(new_card)
        db.commit()
        db.flush()
        return new_card


def update_card_service(user_id: UUID, reviewed_word: ReviewedWord) -> Cards:
    with get_db_session() as db:
        existing_card: Cards = (
            db.query(Cards)
            .where(Cards.user_id == user_id, Cards.id == reviewed_word.wordId)
            .scalar()
        )

        if not existing_card:
            app_logger.warning(
                f"Existing card not found for card with id {reviewed_word.wordId} for user with id {user_id}"
            )
            raise NotFoundError(detail=f"Card with if {reviewed_word.wordId} not found")

        # Update box, stability, last_reviewed and due_at

        existing_card.stability = calculate_new_stability(
            existing_card, reviewed_word.correct, reviewed_word.incorrect
        )

        if reviewed_word.incorrect > 0:
            # Flawless, so next box
            # Check if already highest box
            if existing_card.box != 5:
                existing_card.box += 1

        else:
            # Strict, put back in first box
            existing_card.box = 1

        new_due_date = calculate_due_date(existing_card.box)
        if not new_due_date:
            app_logger.error(
                f"New due date not calculated properly with word id {existing_card.word_id}"
            )
            raise InternalError()

        existing_card.due_at = new_due_date

        existing_card.last_reviewed = reviewed_word.reviewedAt

        db.commit()
        db.refresh(existing_card)

        return existing_card
