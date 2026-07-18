from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.config import settings
from gateway.db.models import Device, Entity, User
from gateway.mqtt.client import MQTTClient
from gateway.mqtt.provisioning import create_device_account, delete_device_account

logger = logging.getLogger(__name__)


class DeviceLimitExceededError(Exception):
    """Raised when a non-admin actor would exceed MAX_DEVICES_PER_USER."""


async def create_device(
    session: AsyncSession,
    mqtt_client: MQTTClient,
    user_id: str,
    name: str,
    *,
    bypass_limit: bool = False,
) -> tuple[Device, str]:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError(f"User {user_id} not found")

    if not bypass_limit:
        count_result = await session.execute(
            select(func.count()).select_from(Device).where(Device.user_id == user_id)
        )
        existing_count = count_result.scalar_one()
        if existing_count >= settings.MAX_DEVICES_PER_USER:
            raise DeviceLimitExceededError(
                f"User {user_id} already has {existing_count} devices "
                f"(limit is {settings.MAX_DEVICES_PER_USER})"
            )

    device = Device(
        user_id=user_id,
        name=name,
        topic_prefix="",
        mqtt_username="",
    )
    session.add(device)
    await session.flush()

    mqtt_username, mqtt_password = await create_device_account(mqtt_client, device.id)
    device.topic_prefix = device.id
    device.mqtt_username = mqtt_username

    await session.commit()
    await session.refresh(device)
    logger.info("created device %s for user %s", device.id, user_id)
    return device, mqtt_password


async def list_devices(session: AsyncSession, user_id: str) -> list[Device]:
    result = await session.execute(select(Device).where(Device.user_id == user_id))
    return list(result.scalars().all())


async def get_device(session: AsyncSession, device_id: str) -> Device | None:
    result = await session.execute(select(Device).where(Device.id == device_id))
    return result.scalar_one_or_none()


async def update_device(session: AsyncSession, device_id: str, name: str) -> Device:
    result = await session.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise ValueError(f"Device {device_id} not found")
    device.name = name
    await session.commit()
    await session.refresh(device)
    logger.info("updated device %s", device_id)
    return device


async def delete_device(
    session: AsyncSession,
    mqtt_client: MQTTClient,
    device_id: str,
) -> None:
    result = await session.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        return

    mqtt_username = device.mqtt_username
    await delete_device_account(mqtt_client, mqtt_username)

    await session.delete(device)
    await session.commit()
    logger.info("deleted device %s", device_id)


async def list_entities(session: AsyncSession, device_id: str) -> list[Entity]:
    result = await session.execute(select(Entity).where(Entity.device_id == device_id))
    return list(result.scalars().all())


async def get_entity(session: AsyncSession, entity_id: str) -> Entity | None:
    result = await session.execute(select(Entity).where(Entity.id == entity_id))
    return result.scalar_one_or_none()
