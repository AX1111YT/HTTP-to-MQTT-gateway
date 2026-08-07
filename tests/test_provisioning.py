from __future__ import annotations

import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest

from gateway.mqtt.provisioning import create_device_account

_RESPONSE_TOPIC = "$CONTROL/dynamic-security/v1/response"


def _message(payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        topic=SimpleNamespace(value=_RESPONSE_TOPIC),
        payload=json.dumps(payload).encode(),
    )


class FakeConnection:
    def __init__(self, submitted_payloads: list[bytes], reply: dict[str, Any]) -> None:
        self._submitted_payloads = submitted_payloads
        self.messages = self._messages(reply)

    async def _messages(self, reply: dict[str, Any]) -> AsyncIterator[SimpleNamespace]:
        yield _message(reply)

    async def __aenter__(self) -> FakeConnection:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def subscribe(self, topic: str) -> None:
        pass

    async def publish(self, topic: str, payload: bytes, qos: int) -> None:
        self._submitted_payloads.append(payload)


class FakeMQTTClient:
    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self._replies = list(replies)
        self.published_payloads: list[bytes] = []

    def publisher_client(self) -> FakeConnection:
        return FakeConnection(self.published_payloads, self._replies.pop(0))


async def _submitted_commands(payloads: list[bytes]) -> list[dict[str, Any]]:
    commands = []
    for payload in payloads:
        commands.append(json.loads(payload)["commands"][0])
    return commands


@pytest.mark.asyncio
async def test_create_device_ignores_success_reply_without_okay_flag() -> None:
    fake_client = FakeMQTTClient(
        [
            {"responses": [{"command": "createRole"}]},
            {"responses": [{"command": "createClient"}]},
        ]
    )

    username, _ = await create_device_account(fake_client, "a1b2c3d4e5")

    assert username == "device_a1b2c3d4e5"
    commands = await _submitted_commands(fake_client.published_payloads)
    assert [command["command"] for command in commands] == [
        "createRole",
        "createClient",
    ]


@pytest.mark.asyncio
async def test_device_creation_raises_with_broker_error_message() -> None:
    fake_client = FakeMQTTClient(
        [{"responses": [{"command": "createRole", "error": "Role already exists"}]}]
    )

    with pytest.raises(RuntimeError, match="Role already exists"):
        await create_device_account(fake_client, "a1b2c3d4e5")


@pytest.mark.asyncio
async def test_device_creation_raises_without_reply() -> None:
    fake_client = FakeMQTTClient([{}])

    with pytest.raises(RuntimeError, match="Failed to create MQTT role"):
        await create_device_account(fake_client, "a1b2c3d4e5")
