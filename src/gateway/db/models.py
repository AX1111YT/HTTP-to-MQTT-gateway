from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateway.db.base import Base


def _uuid7() -> str:
    return str(uuid.uuid7())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid7)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_lookup_hash: Mapped[str] = mapped_column(
        Text, unique=True, nullable=False, index=True
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    key_rotated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    devices: Mapped[list[Device]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid7)
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    topic_prefix: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    mqtt_username: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped[User] = relationship(back_populates="devices")
    entities: Mapped[list[Entity]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("device_id", "object_id"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid7)
    device_id: Mapped[str] = mapped_column(
        Text, ForeignKey("devices.id"), nullable=False
    )
    component_type: Mapped[str] = mapped_column(Text, nullable=False)
    object_id: Mapped[str] = mapped_column(Text, nullable=False)
    friendly_name: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_topic: Mapped[str] = mapped_column(Text, nullable=False)
    command_topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    device: Mapped[Device] = relationship(back_populates="entities")
