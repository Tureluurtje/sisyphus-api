from uuid import UUID
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.schema.http.words import GetStacksResponse
from api.schema.internal.words import DueWord, ReviewedWord, LoadWordList, Stack
from api.models.words import Cards, Chapters, Lists, Reviews, Words
from api.models.auth import User
from api.database import get_db_session
from api.logging_config import app_logger
from api.schema.internal.errors import InternalError



def _ensure_aware(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware in UTC.

    Many stored datetimes may be naive (no tzinfo). Treat naive values as
    UTC to allow consistent comparisons with timezone-aware `now()`.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def calculate_due_date(box: int) -> Optional[datetime]:
    now = datetime.now()
    match box:
        case 0:
            return now + timedelta(days=1)
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
    days_since_review = (_ensure_aware(datetime.now(timezone.utc)) - _ensure_aware(card.last_reviewed)).days

    if days_since_review < 1:
        days_since_review = 1

    # growth from successful recalls
    growth = 0.05 * accuracy * min(days_since_review, 30)

    # penalty from mistakes
    penalty = 0.08 * (1 - accuracy)

    new_stability = stability + growth - penalty

    return max(0.05, min(1.0, new_stability))

def calculate_learnyear(current_date: Optional[datetime] = None) -> str:
    current_date = current_date or datetime.now()

    start_month = 9
    if current_date.month >= start_month:
        start_year = current_date.year
    else:
        start_year = current_date.year - 1

    end_year = start_year + 1

    return f"{start_year % 100:02d}-{end_year % 100:02d}"

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



def get_due_words_service(user_id: UUID, limit: Optional[int] = None, offset: Optional[int] = 0) -> list[DueWord]:
    if limit is not None and limit <= 0:
        limit = None
    if offset is not None and offset <= 0:
        offset = None

    with get_db_session() as db:
        # First query for current year
        user = db.query(User).where(User.id == user_id).scalar()

        learnyear = calculate_learnyear()

        # Then find cards for this year
        due_words = (
            db.query(Words)
            .join(Chapters, Words.chapter_id == Chapters.id)
            .join(Lists, Chapters.list_id == Lists.id)
            .outerjoin(
                Cards,
                (Cards.word_id == Words.id) &
                (Cards.user_id == user_id)
            )
            .where(
                Lists.schoolyear == learnyear,
                Lists.schoolgrade == user.grade,
                or_(
                    Cards.id.is_(None),  # never learned
                    Cards.due_at <= datetime.now(timezone.utc)  # due
                )
            )
            .limit(limit)
            .offset(offset)
            .all()
        )

        due_word_model_words: list[DueWord] = []
        for word in due_words:
            due_word_model_words.append(DueWord(
                wordId=word.id,
                chapterId=word.chapter_id,
                word=word.word,
                translation=word.translation
            ))
        return due_word_model_words

def submit_word_review_service(user_id: UUID, reviews: list[ReviewedWord]) -> list[Cards]:
    updated_cards: list[Cards] = []
    with get_db_session() as db:
        try:
            for word in reviews:
                updated_card = update_card_service(user_id, word, db)
                updated_cards.append(updated_card)
                if word.incorrect == 0:
                    rating = 1
                else:
                    rating = 0
                add_review_entry(
                    user_id=user_id,
                    card_id=updated_card.id,
                    rating=rating,
                    response_time_ms=word.averageResponseTimeMs,
                    reviewed_at=word.reviewedAt,
                    db=db
                )
            db.commit()
        except:
            db.rollback()

    return updated_cards

def add_card_service(
    user_id: UUID,
    word_id: UUID,
    reviewed_at: datetime,
    db: Optional[Session] = None
) -> Cards:
    due_at = calculate_due_date(0)
    if db:
        new_card = Cards(
            user_id=user_id,
            word_id=word_id,
            due_at=due_at,
            last_reviewed=reviewed_at,
            box=0
        )

        db.add(new_card)
        db.flush()
        db.refresh(new_card)
        return new_card

    with get_db_session() as db:
        new_card = Cards(user_id=user_id, word_id=word_id, box=0)
        db.add(new_card)
        db.commit()
        db.refresh(new_card)
        return new_card


def update_card_service(user_id: UUID, reviewed_word: ReviewedWord, db: Session) -> Cards:
    existing_card: Cards = (
        db.query(Cards)
        .where(Cards.user_id == user_id, Cards.word_id == reviewed_word.wordId)
        .first()
    )

    if not existing_card:
        # Create card
        existing_card = add_card_service(
            user_id=user_id,
            word_id=reviewed_word.wordId,
            reviewed_at=reviewed_word.reviewedAt,
            db=db
        )

    # Update box, stability, last_reviewed and due_at

    existing_card.stability = calculate_new_stability(
        existing_card, reviewed_word.correct, reviewed_word.incorrect
    )

    if reviewed_word.incorrect == 0:
        # Flawless, so next box
        # Check if already highest box
        if existing_card.box != 5:
            existing_card.box += 1

    else:
        # Strict, put back in first box
        # TODO: Add non strict version, users choice
        existing_card.box = 1

    new_due_date = calculate_due_date(existing_card.box)
    if not new_due_date:
        app_logger.error(
            f"New due date not calculated properly with word id {existing_card.word_id}"
        )
        raise InternalError()

    existing_card.due_at = new_due_date

    existing_card.last_reviewed = reviewed_word.reviewedAt

    db.flush()

    return existing_card

def add_review_entry(
    user_id: UUID,
    card_id: UUID,
    rating: int,
    response_time_ms: int,
    reviewed_at: datetime,
    db: Session
) -> None:
    if rating not in (0,1 ):
        app_logger.error(f"rating for card id '{card_id}' does not have a correct rating(0 or 1).")
        raise InternalError()

    new_review_entry = Reviews(
        user_id=user_id,
        card_id=card_id,
        rating=rating,
        response_time_ms=response_time_ms,
    )
    db.add(new_review_entry)
    db.flush()

def get_stack_service(
    user_id: UUID,
    stack_id: Optional[int] = None,
    all_stacks: Optional[bool] = None,
) -> GetStacksResponse | Stack:
    if not all_stacks and stack_id is None:
        app_logger.error("either `stack_id` or `all_stacks` must be given")
        raise InternalError()

    if not all_stacks and stack_id not in (0, 1, 2, 3, 4, 5):
        app_logger.error("`stack_id` parameter not a valid stack id")
        raise InternalError()

    with get_db_session() as db:
        query = (
            db.query(Cards, Words)
            .join(Words, Words.id == Cards.word_id)
            .where(Cards.user_id == user_id)
        )

        if not all_stacks:
            query = query.where(Cards.box == stack_id)

        rows = query.all()
        word_amount = len(rows)

        if all_stacks:
            stacks: dict[int, list[DueWord]] = {i: [] for i in range(6)}
            for card, word in rows:
                if card.box in stacks:
                    stacks[card.box].append(DueWord(
                        wordId=word.id,
                        chapterId=word.chapter_id,
                        word=word.word,
                        translation=word.translation
                    ))
                else:
                    app_logger.error(f"Word with id {word.id} has no valid box id set")

            stack_0, stack_1, stack_2, stack_3, stack_4, stack_5 = (
                stacks[0], stacks[1], stacks[2], stacks[3], stacks[4], stacks[5]
            )

            stack_word_list = [stack_0, stack_1, stack_2, stack_3, stack_4, stack_5]
            stack_list: list[Stack] = [Stack(stack_id=i, wordAmount=len(stack), words=stack) for i, stack in enumerate(stack_word_list)]
            return GetStacksResponse(
                wordAmount=word_amount,
                stacks=stack_list
            )

        else:
            assert stack_id is not None # Narrows Optional[int] to type int for the type checker
            words = [word for _, word in rows]
            return Stack(stack_id=stack_id, wordAmount=len(words), words=words)
