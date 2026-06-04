from uuid import UUID
from datetime import datetime, timedelta
from typing import Optional

from api.schema.internal.words import ReviewedWord
from api.models.words import Cards
from api.database import get_db_session
from api.logging_config import app_logger, error_logger


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
            day = min(now.day, (datetime(year, month % 12 + 1, 1) - timedelta(days=1)).day) if month != 12 else min(now.day, 31)
            return now.replace(year=year, month=month, day=day)
        case _:
            app_logger.warn(f"box number of {box} not in allowed numbers(0-5)")
            return None


def get_due_words_service(user_id: UUID):


def add_card_service(
    user_id: UUID,
    word_id: UUID
):
    with get_db_session() as db:
        new_card = Cards(
            user_id=user_id,
            word_id=word_id,
            box=0
        )

def update_card_service(
    user_id: UUID,
    data: ReviewedWord
):
    with get_db_session() as db:
        existing_card = db.query(Cards).where(
            Cards.user_id ==
        ).scalar()
