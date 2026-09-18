from uuid import UUID

from pydantic import BaseModel, RootModel


class LeaderboardRow(BaseModel):
    user_id: UUID
    rank: int
    username: str
    xp: int


class LeaderboardList(RootModel[list[LeaderboardRow]]):
    pass
