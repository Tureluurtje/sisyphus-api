from datetime import datetime
import uuid

from sqlalchemy import (
    BIGINT,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    func,
    Float,
    UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import List

from api.database import Base

class Lists(Base):
    __tablename__ = "lists"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    schoolyear: Mapped[str] = mapped_column(Text, nullable=False)
    schoolgrade: Mapped[int] = mapped_column(BIGINT, nullable=False)

    chapters: Mapped[list["Chapters"]] = relationship(
        "Chapters",
        back_populates="list",
        cascade="all, delete-orphan",
    )

class Chapters(Base):
    __tablename__ = "chapters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)

    list: Mapped["Lists"] = relationship(
        "Lists",
        back_populates="chapters",
    )

    words: Mapped[List["Words"]] = relationship(
        "Words",
        back_populates="chapter",
        cascade="all, delete-orphan",
    )

class Words(Base):
    __tablename__ = "words"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    chapter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chapters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    word: Mapped[str] = mapped_column(Text, nullable=False)
    translation: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    target_date: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    chapter: Mapped["Chapters"] = relationship(
        "Chapters",
        back_populates="words",
    )

    cards: Mapped[list["Cards"]] = relationship(
        "Cards",
        back_populates="word",
        cascade="all, delete-orphan",
    )

class Cards(Base):
    __tablename__ = "cards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    word_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("words.id", ondelete="CASCADE"),
        nullable=False,
    )

    box: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    due_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    last_reviewed: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    stability: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    word: Mapped["Words"] = relationship(
        "Words",
        back_populates="cards",
    )

    reviews: Mapped[list["Reviews"]] = relationship(
        "Reviews",
        back_populates="card",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        {"extend_existing": True}, UniqueConstraint("user_id", "word_id", name="uq_cards_user_word"),
    )

class Reviews(Base):
    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cards.id", ondelete="CASCADE"),
        nullable=False,
    )

    rating: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    response_time_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    card: Mapped["Cards"] = relationship(
        "Cards",
        back_populates="reviews",
    )
