from uuid import UUID

from sqlalchemy.orm import Session as DbSession

from api.models.auth import User
from api.models.words import Cards, Chapters, Lists, Words
from api.schema.http.leaderboard import LeaderboardList, LeaderboardRow
from api.schema.internal.errors import UserNotFoundError


def _get_users_from_class(user_id: UUID, db: DbSession) -> list[User]:
    user = db.get(User, user_id)
    if not user:
        raise UserNotFoundError()

    # Make sure user is not dev account
    return db.query(User).filter(User.grade == user.grade, User.dev == False).all()


def _calculate_xp(user_id: UUID, db: DbSession) -> int:
    user = db.get(User, user_id)

    if not user:
        raise UserNotFoundError()

    user_cards = (
        db.query(Cards)
        .join(Words, Cards.word_id == Words.id)
        .join(Chapters, Words.chapter_id == Chapters.id)
        .join(Lists, Chapters.list_id == Lists.id)
        .filter(
            Cards.user_id == user_id,
            Lists.schoolgrade == user.grade,
        )
        .all()
    )

    total_xp = 0

    for card in user_cards:
        total_xp += card.box * 1

    return total_xp


def get_full_leaderboard(user_id: UUID, db: DbSession) -> LeaderboardList:
    user = db.get(User, user_id)

    if not user:
        raise UserNotFoundError()

    class_user_list = _get_users_from_class(user_id, db)

    per_user_xp: dict[User, int] = {}

    for class_member in class_user_list:
        per_user_xp[class_member] = _calculate_xp(class_member.id, db)

    sorted_members = sorted(per_user_xp.items(), key=lambda item: item[1], reverse=True)

    return LeaderboardList(
        root=[
            LeaderboardRow(user_id=user.id, rank=rank, username=user.username, xp=xp)
            for rank, (user, xp) in enumerate(sorted_members, start=1)
        ]
    )


def get_me_leaderboard(user_id: UUID, db: DbSession) -> LeaderboardRow:
    full_leaderboard = get_full_leaderboard(user_id, db)

    for row in full_leaderboard.root:
        if user_id == row.user_id:
            return row

    raise UserNotFoundError()
