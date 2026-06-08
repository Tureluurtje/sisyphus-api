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
    reviewedAt: datetime
    correct: int
    incorrect: int
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


class LoadWord(BaseModel):
    word: str
    translation: str
    targetDate: datetime

class LoadChapter(BaseModel):
    name: str
    words: list[LoadWord]


class LoadWordList(BaseModel):
    schoolYear: str
    schoolGrade: int
    chapters: list[LoadChapter]
