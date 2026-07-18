from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import aiomqtt
from sqlalchemy import select

from gateway.config import settings
from gateway.db.base import async_session_factory
from gateway.db.models import Device, Entity
from gateway.mqtt.client import MQTTClient

logger = logging.getLogger(__name__)


def _parse_discovery_topic(topic: str) -> tuple[str, str, str, str] | None:
    parts = topic.split("/")
    if len(parts) < 4:
        return None
    prefix = parts[0]
    if prefix != settings.MQTT_DISCOVERY_PREFIX:
        return None
    component_type = parts[1]
    node_name = parts[2]
    object_id = parts[3]
    return component_type, node_name, object_id, topic


def _parse_device_topic(topic: str) -> tuple[str, str, str, str] | None:
    parts = topic.split("/")
    if len(parts) < 4:
        return None
    topic_prefix = parts[0]
    component_type = parts[1]
    object_id = parts[2]
    suffix = parts[3]
    return topic_prefix, component_type, object_id, suffix


def _validate_scoped_topic(
    topic: str | None, device: Device, field_name: str
) -> str | None:
    if topic is None:
        return None
    allowed_prefix = f"{device.topic_prefix}/"
    if not topic.startswith(allowed_prefix):
        logger.warning(
            "rejecting out-of-scope %s %r from device %s (topic_prefix=%s)",
            field_name,
            topic,
            device.id,
            device.topic_prefix,
        )
        return None
    return topic


async def _upsert_entity(
    session: Any,
    device: Device,
    component_type: str,
    object_id: str,
    config: dict[str, Any],
) -> None:
    default_state_topic = f"{device.topic_prefix}/{component_type}/{object_id}/state"
    state_topic = _validate_scoped_topic(
        config.get("state_topic", default_state_topic), device, "state_topic"
    )
    if state_topic is None:
        logger.warning(
            "dropping discovery message for %s/%s on device %s: invalid state_topic",
            component_type,
            object_id,
            device.id,
        )
        return

    command_topic = _validate_scoped_topic(
        config.get("command_topic"), device, "command_topic"
    )

    stmt = select(Entity).where(
        Entity.device_id == device.id,
        Entity.object_id == object_id,
    )
    result = await session.execute(stmt)
    entity = result.scalar_one_or_none()

    if entity is None:
        entity = Entity(
            device_id=device.id,
            component_type=component_type,
            object_id=object_id,
            friendly_name=config.get("name", object_id),
            unit=config.get("unit_of_measurement"),
            device_class=config.get("device_class"),
            state_topic=state_topic,
            command_topic=command_topic,
        )
        session.add(entity)
    else:
        entity.component_type = component_type
        entity.friendly_name = config.get("name", object_id)
        entity.unit = config.get("unit_of_measurement")
        entity.device_class = config.get("device_class")
        entity.state_topic = state_topic
        entity.command_topic = command_topic


async def _handle_discovery_message(topic: str, payload: bytes) -> None:
    parsed = _parse_discovery_topic(topic)
    if parsed is None:
        return

    component_type, node_name, object_id, _ = parsed

    try:
        config = json.loads(payload.decode())
    except json.JSONDecodeError, UnicodeDecodeError:
        logger.warning("invalid discovery payload on %s", topic)
        return

    async with async_session_factory() as session:
        stmt = select(Device).where(Device.topic_prefix == node_name)
        result = await session.execute(stmt)
        device = result.scalar_one_or_none()

        if device is None:
            logger.debug("discovery for unknown device %s", node_name)
            return

        await _upsert_entity(session, device, component_type, object_id, config)
        await session.commit()

    logger.debug(
        "upserted entity %s/%s for device %s", component_type, object_id, node_name
    )


async def _handle_state_message(topic: str, payload: bytes) -> None:
    parsed = _parse_device_topic(topic)
    if parsed is None:
        return

    topic_prefix, component_type, object_id, _ = parsed

    async with async_session_factory() as session:
        device_stmt = select(Device).where(Device.topic_prefix == topic_prefix)
        device_result = await session.execute(device_stmt)
        device = device_result.scalar_one_or_none()

        if device is None:
            return

        entity_stmt = select(Entity).where(
            Entity.device_id == device.id,
            Entity.object_id == object_id,
        )
        entity_result = await session.execute(entity_stmt)
        entity = entity_result.scalar_one_or_none()

        if entity is None:
            return

        entity.current_value = payload.decode(errors="replace")
        entity.last_updated_at = datetime.now(timezone.utc)
        await session.commit()


async def _handle_availability_message(topic: str, payload: bytes) -> None:
    parsed = _parse_device_topic(topic)
    if parsed is None:
        return

    topic_prefix, _, _, _ = parsed
    value = payload.decode(errors="replace").strip().lower()
    online = value == "online"

    async with async_session_factory() as session:
        stmt = select(Device).where(Device.topic_prefix == topic_prefix)
        result = await session.execute(stmt)
        device = result.scalar_one_or_none()

        if device is None:
            return

        device.online = online
        device.last_seen_at = datetime.now(timezone.utc)
        await session.commit()


async def _load_device_topic_prefixes() -> list[str]:
    async with async_session_factory() as session:
        stmt = select(Device.topic_prefix)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def run_ingestor(mqtt_client: MQTTClient) -> None:
    discovery_prefix = settings.MQTT_DISCOVERY_PREFIX
    delay = 1.0

    while True:
        try:
            prefixes = await _load_device_topic_prefixes()
            topics: list[tuple[str, int]] = [
                (f"{discovery_prefix}/#", 0),
            ]
            for prefix in prefixes:
                topics.append((f"{prefix}/+/+/state", 0))
                topics.append((f"{prefix}/+/+/availability", 0))

            async with mqtt_client.ingestor_client as client:
                for topic, qos in topics:
                    await client.subscribe(topic, qos=qos)

                logger.info("ingestor subscribed to %d topics", len(topics))
                delay = 1.0

                async for message in client.messages:
                    topic = message.topic.value
                    if not topic:
                        continue

                    if topic.startswith(f"{discovery_prefix}/"):
                        await _handle_discovery_message(topic, message.payload)
                    elif topic.endswith("/state"):
                        await _handle_state_message(topic, message.payload)
                    elif topic.endswith("/availability"):
                        await _handle_availability_message(topic, message.payload)

        except aiomqtt.MqttError:
            logger.warning(
                "ingestor mqtt connection lost, reconnecting in %.1fs", delay
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2.0, 60.0)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ingestor error")
            await asyncio.sleep(delay)
            delay = min(delay * 2.0, 60.0)
