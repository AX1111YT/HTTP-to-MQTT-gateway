from __future__ import annotations

import json
import logging

from gateway.mqtt.client import MQTTClient

logger = logging.getLogger(__name__)


async def publish_command(
    mqtt_client: MQTTClient,
    command_topic: str,
    payload: dict[str, object],
) -> None:
    raw = json.dumps(payload).encode()
    async with mqtt_client.publisher_client() as client:
        await client.publish(command_topic, raw, qos=1)
    logger.debug("published command to %s", command_topic)
