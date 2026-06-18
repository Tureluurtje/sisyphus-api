from pydantic import BaseModel

#from api.models.words import Cards
from api.schema.internal.words import DueWord, ReviewedWord, Stack


class DueWordsResponse(BaseModel):
    wordAmount: int
    words: list[DueWord]


class WordReviewRequest(BaseModel):
    reviews: list[ReviewedWord]


class WordReviewResponse(BaseModel):
    success: bool

class GetStacksResponse(BaseModel):
    wordAmount: int
    stacks: list[Stack]
