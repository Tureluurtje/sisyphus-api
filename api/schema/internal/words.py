from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class Word(BaseModel):
    wordId: UUID
    chapterId: UUID
    word: str
    translation: str
    targetDate: datetime

class DueWord(BaseModel):
    wordId: UUID
    chapterId: UUID
    word: str
    translation: str

class ReviewedWord(BaseModel):
    wordId: UUID
    right: int
    wrong: int
    averageResponseTimeMs: int

class Chapter(BaseModel):
    chapterId: UUID
    name: str
    words: list[Word]

class WordList(BaseModel):
    listId: UUID
    schoolYear: str
    schoolGrade: int
    chapters: list[Chapter]
