from __future__ import annotations

import asyncio
import logging
import ssl

import aiomqtt

from gateway.config import settings

logger = logging.getLogger(__name__)

_BACKOFF_INITIAL = 1.0
_BACKOFF_MAX = 60.0
_BACKOFF_FACTOR = 2.0


class MQTTClient:
    """Manages MQTT connections for the gateway."""

    def __init__(self) -> None:
        self._ingestor_task: asyncio.Task[None] | None = None

    def _make_client(self) -> aiomqtt.Client:
        tls_context = ssl.create_default_context()
        if settings.MQTT_CA_CERTS:
            tls_context.load_verify_locations(settings.MQTT_CA_CERTS)
        return aiomqtt.Client(
            hostname=settings.MQTT_BROKER_HOST,
            port=settings.MQTT_BROKER_PORT,
            username=settings.MQTT_ADMIN_USERNAME,
            password=settings.MQTT_ADMIN_PASSWORD,
            tls_context=tls_context,
        )

    async def start(self) -> None:
        from gateway.mqtt.ingestor import run_ingestor

        self._ingestor_task = asyncio.create_task(run_ingestor(self))
        logger.info("mqtt client started")

    async def stop(self) -> None:
        if self._ingestor_task is not None:
            self._ingestor_task.cancel()
            try:
                await self._ingestor_task
            except asyncio.CancelledError:
                pass
        logger.info("mqtt client stopped")

    @property
    def ingestor_client(self) -> aiomqtt.Client:
        return self._make_client()

    def publisher_client(self) -> aiomqtt.Client:
        return self._make_client()


mqtt_client = MQTTClient()
