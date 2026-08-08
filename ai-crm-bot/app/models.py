import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import CHAR, TypeDecorator

from .db import Base


class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def __init__(self, as_uuid: bool = False, *args, **kwargs):
        self.as_uuid = as_uuid
        super().__init__(*args, **kwargs)

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=self.as_uuid))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if self.as_uuid and isinstance(value, uuid.UUID):
            return str(value)
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if self.as_uuid:
            return uuid.UUID(value)
        return value


class JSONType(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class State:
    COLLECTING = "COLLECTING"
    EXTRACTING = "EXTRACTING"
    CLARIFYING = "CLARIFYING"
    CONFIRMING = "CONFIRMING"
    CORRECTING = "CORRECTING"
    HANDED_OFF = "HANDED_OFF"
    SUBMITTED = "SUBMITTED"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
        nullable=False,
    )
    state: Mapped[str] = mapped_column(
        String,
        default=State.COLLECTING,
        nullable=False,
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    field_retry_count: Mapped[dict] = mapped_column(
        JSONType,
        default=dict,
    )
    draft_json: Mapped[dict] = mapped_column(
        JSONType,
        default=dict,
    )
    human_takeover: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(as_uuid=True),
        ForeignKey("conversations.id"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    raw_response: Mapped[dict | None] = mapped_column(
        JSONType,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )


class ExtractionSnapshot(Base):
    __tablename__ = "extraction_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(as_uuid=True),
        ForeignKey("conversations.id"),
        index=True,
        nullable=False,
    )
    extracted_json: Mapped[dict] = mapped_column(
        JSONType,
        default=dict,
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    missing_fields: Mapped[list] = mapped_column(
        JSONType,
        default=list,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )


class CrmSubmission(Base):
    __tablename__ = "crm_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(as_uuid=True),
        ForeignKey("conversations.id"),
        index=True,
        nullable=False,
    )
    amo_lead_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    amo_contact_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(
        JSONType,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )


class CrmQueueItem(Base):
    __tablename__ = "crm_queue_items"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(as_uuid=True),
        ForeignKey("conversations.id"),
        index=True,
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(
        JSONType,
        default=dict,
    )
    existing_contact_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String,
        default="pending",
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class Handoff(Base):
    __tablename__ = "handoffs"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(as_uuid=True),
        ForeignKey("conversations.id"),
        index=True,
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    manager_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class TelegramContact(Base):
    __tablename__ = "telegram_contacts"

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )
    amo_contact_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    last_order_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )