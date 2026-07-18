from __future__ import annotations

import json
import logging
import secrets
from typing import Any

from gateway.config import settings
from gateway.mqtt.client import MQTTClient

logger = logging.getLogger(__name__)

_DYNAMIC_SECURITY_TOPIC = "$CONTROL/dynamic-security/v1"
_DYNAMIC_SECURITY_RESPONSE_TOPIC = "$CONTROL/dynamic-security/v1/response"


async def _send_command(
    mqtt_client: MQTTClient, command: dict[str, Any]
) -> dict[str, Any]:
    payload = json.dumps({"commands": [command]}).encode()
    response: dict[str, Any] = {}

    async with mqtt_client.publisher_client() as client:
        await client.subscribe(_DYNAMIC_SECURITY_RESPONSE_TOPIC)
        await client.publish(_DYNAMIC_SECURITY_TOPIC, payload, qos=1)
        async for message in client.messages:
            if message.topic.value == _DYNAMIC_SECURITY_RESPONSE_TOPIC:
                response.update(json.loads(message.payload.decode()))
                break

    return response


def _generate_password() -> str:
    return secrets.token_urlsafe(32)


async def create_device_account(
    mqtt_client: MQTTClient, device_id: str
) -> tuple[str, str]:
    username = f"device_{device_id}"
    password = _generate_password()
    role_name = f"role_{device_id}"

    create_role_command = {
        "command": "createRole",
        "rolename": role_name,
        "acls": [
            {
                "acltype": "publishClientSend",
                "topic": f"{device_id}/#",
                "allow": True,
            },
            {
                "acltype": "publishClientReceive",
                "topic": f"{device_id}/#",
                "allow": True,
            },
            {
                "acltype": "subscribePattern",
                "topic": f"{device_id}/#",
                "allow": True,
            },
            {
                "acltype": "publishClientSend",
                "topic": f"{settings.MQTT_DISCOVERY_PREFIX}/+/{device_id}/+/config",
                "allow": True,
            },
        ],
    }

    create_client_command = {
        "command": "createClient",
        "username": username,
        "password": password,
        "roles": [{"rolename": role_name}],
    }

    response = await _send_command(mqtt_client, create_role_command)
    if not response.get("responses", [{}])[0].get("okay"):
        error = response.get("responses", [{}])[0].get("error", "unknown")
        logger.error("failed to create mqtt role: %s", error)
        raise RuntimeError(f"Failed to create MQTT role: {error}")

    response = await _send_command(mqtt_client, create_client_command)
    if not response.get("responses", [{}])[0].get("okay"):
        error = response.get("responses", [{}])[0].get("error", "unknown")
        logger.error("failed to create mqtt client: %s", error)
        raise RuntimeError(f"Failed to create MQTT client: {error}")

    logger.info("created mqtt account for device %s", device_id)
    return username, password


async def delete_device_account(mqtt_client: MQTTClient, mqtt_username: str) -> None:
    delete_client_command = {
        "command": "deleteClient",
        "username": mqtt_username,
    }

    response = await _send_command(mqtt_client, delete_client_command)
    if not response.get("responses", [{}])[0].get("okay"):
        error = response.get("responses", [{}])[0].get("error", "unknown")
        logger.error("failed to delete mqtt client: %s", error)
        raise RuntimeError(f"Failed to delete MQTT client: {error}")

    role_name = f"role_{mqtt_username.removeprefix('device_')}"
    delete_role_command = {
        "command": "deleteRole",
        "rolename": role_name,
    }

    response = await _send_command(mqtt_client, delete_role_command)
    if not response.get("responses", [{}])[0].get("okay"):
        error = response.get("responses", [{}])[0].get("error", "unknown")
        logger.warning("failed to delete mqtt role: %s", error)

    logger.info("deleted mqtt account %s", mqtt_username)
