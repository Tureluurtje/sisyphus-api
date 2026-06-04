from pydantic import BaseModel
from uuid import UUID

from api.schema.internal.words import (
    DueWord,
    ReviewedWord
)

class DueWordsResponse(BaseModel):
    wordAmount: int
    words: list[DueWord]

class WordReviewRequest(BaseModel):
    sessionId: UUID
    reviews: list[ReviewedWord]
