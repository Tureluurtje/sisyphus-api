from __future__ import annotations

from datetime import datetime
import uuid
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    text,
    Enum as SQLEnum,
)
from sqlalchemy import Boolean, DateTime, ForeignKey, String, func, text, BIGINT
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base

from enum import Enum as PyEnum


class VerificationTokenPurposes(PyEnum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"

class OauthProviders(PyEnum):
    GOOGLE = "google"
    APPLE = "apple"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    grade: Mapped[int] = mapped_column(BIGINT, nullable=False)

    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    # Nullable password because oauth accounts don't have a password
    password: Mapped[str] = mapped_column(String, nullable=True)

    verified: Mapped[bool] = mapped_column(Boolean, default=False)

    dev: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # relationships
    tokens: Mapped[List["Tokens"]] = relationship(
        argument="Tokens", back_populates="user", cascade="all, delete-orphan"
    )
    verification_tokens: Mapped[List["VerificationTokens"]] = relationship(
        argument="VerificationTokens",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    oauth_accounts: Mapped[List["OAuthAccount"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # revoked_access_tokens: Mapped[List["RevokedAccessTokens"]] = relationship(
    #    argument="RevokedAccessTokens",
    #    back_populates="user",
    #    cascade="all, delete-orphan",
    # )


class Tokens(Base):
    __tablename__ = "tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    replaced_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    # relationships
    user: Mapped["User"] = relationship(argument="User", back_populates="tokens")


class RevokedAccessTokens(Base):
    __tablename__ = "revoked_access_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    jti: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False
    )


class VerificationTokens(Base):
    __tablename__ = "verification_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    purpose: Mapped[str] = mapped_column(
        SQLEnum(VerificationTokenPurposes, name="status_enum"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # relationships
    user: Mapped["User"] = relationship(argument="User")


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    provider: Mapped[str] = mapped_column(
        SQLEnum(OauthProviders, name="oauth_providers_enum"),
        nullable=False,
    )

    provider_user_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        back_populates="oauth_accounts"
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_user_id",
            name="uq_oauth_provider_user",
        ),
    )
