from __future__ import annotations

import asyncio
import json
import logging
import secrets
from collections.abc import AsyncIterator
from typing import Any, Protocol

from gateway.config import settings

logger = logging.getLogger(__name__)

_DYNAMIC_SECURITY_TOPIC = "$CONTROL/dynamic-security/v1"
_DYNAMIC_SECURITY_RESPONSE_TOPIC = "$CONTROL/dynamic-security/v1/response"
_COMMAND_TIMEOUT_SECONDS = 10.0


class CommandConnection(Protocol):
    async def __aenter__(self) -> CommandConnection: ...

    async def __aexit__(self, *args: Any) -> None: ...

    async def subscribe(self, topic: str) -> Any: ...

    async def publish(self, topic: str, payload: bytes, qos: int) -> None: ...

    @property
    def messages(self) -> AsyncIterator[Any]: ...


class CommandClient(Protocol):
    def publisher_client(self) -> CommandConnection: ...


async def _send_command(
    mqtt_client: CommandClient, command: dict[str, Any]
) -> dict[str, Any]:
    payload = json.dumps({"commands": [command]}).encode()
    response: dict[str, Any] = {}

    async with mqtt_client.publisher_client() as client:
        await client.subscribe(_DYNAMIC_SECURITY_RESPONSE_TOPIC)
        await client.publish(_DYNAMIC_SECURITY_TOPIC, payload, qos=1)
        async with asyncio.timeout(_COMMAND_TIMEOUT_SECONDS):
            async for message in client.messages:
                if message.topic.value == _DYNAMIC_SECURITY_RESPONSE_TOPIC:
                    response.update(json.loads(message.payload.decode()))
                    break

    return response


def _reply_error(response: dict[str, Any]) -> str | None:
    replies = response.get("responses")
    if not isinstance(replies, list) or not replies:
        return "no reply from broker"
    error = replies[0].get("error")
    return error if error is not None else None


def _generate_password() -> str:
    return secrets.token_urlsafe(32)


async def create_device_account(
    mqtt_client: CommandClient, device_id: str
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
    if error := _reply_error(response):
        logger.error("failed to create mqtt role: %s", error)
        raise RuntimeError(f"Failed to create MQTT role: {error}")

    response = await _send_command(mqtt_client, create_client_command)
    if error := _reply_error(response):
        logger.error("failed to create mqtt client: %s", error)
        raise RuntimeError(f"Failed to create MQTT client: {error}")

    logger.info("created mqtt account for device %s", device_id)
    return username, password


async def delete_device_account(mqtt_client: CommandClient, mqtt_username: str) -> None:
    delete_client_command = {
        "command": "deleteClient",
        "username": mqtt_username,
    }

    response = await _send_command(mqtt_client, delete_client_command)
    if error := _reply_error(response):
        logger.error("failed to delete mqtt client: %s", error)
        raise RuntimeError(f"Failed to delete MQTT client: {error}")

    role_name = f"role_{mqtt_username.removeprefix('device_')}"
    delete_role_command = {
        "command": "deleteRole",
        "rolename": role_name,
    }

    response = await _send_command(mqtt_client, delete_role_command)
    if error := _reply_error(response):
        logger.warning("failed to delete mqtt role: %s", error)

    logger.info("deleted mqtt account %s", mqtt_username)
