from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from gateway.db.models import Device, Entity
from gateway.mqtt.client import MQTTClient
from gateway.mqtt.publisher import publish_command
from gateway.schemas.command import (
    ClimateCommand,
    CoverCommand,
    FanCommand,
    LightCommand,
    LockCommand,
    NumberCommand,
    SensorCommand,
    SwitchCommand,
)

logger = logging.getLogger(__name__)

_COMMAND_MAP: dict[str, type[BaseModel] | None] = {
    "switch": SwitchCommand,
    "light": LightCommand,
    "sensor": SensorCommand,
    "binary_sensor": None,  # read-only
    "climate": ClimateCommand,
    "number": NumberCommand,
    "fan": FanCommand,
    "lock": LockCommand,
    "cover": CoverCommand,
}


async def send_command(
    mqtt_client: MQTTClient,
    device: Device,
    entity: Entity,
    payload: dict[str, Any],
) -> None:
    if not device.online:
        raise ValueError(f"Device {device.id} is offline")

    model_cls = _COMMAND_MAP.get(entity.component_type)
    if model_cls is None:
        raise ValueError(
            f"Component type {entity.component_type} does not accept commands"
        )

    command = model_cls.model_validate(payload)

    if entity.command_topic is None:
        raise ValueError(f"Entity {entity.id} has no command topic")

    await publish_command(
        mqtt_client,
        entity.command_topic,
        command.model_dump(exclude_none=True),
    )
    logger.info(
        "sent %s command to entity %s on device %s",
        entity.component_type,
        entity.id,
        device.id,
    )
