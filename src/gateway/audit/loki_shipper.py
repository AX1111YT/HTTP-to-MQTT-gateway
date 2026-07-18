from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import httpx

from gateway.config import settings

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50
_FLUSH_INTERVAL = 5.0
_LOKI_TIMEOUT = 5.0

_batch_lock = threading.Lock()
_batch: list[dict[str, Any]] = []
_flush_timer: threading.Timer | None = None


def _push_to_loki(entries: list[dict[str, Any]]) -> None:
    if not settings.LOKI_PUSH_URL:
        return

    streams: list[dict[str, Any]] = []
    values: list[list[str]] = []
    for entry in entries:
        ts_ns = str(int(time.time() * 1e9))
        values.append([ts_ns, json.dumps(entry, ensure_ascii=False)])

    streams.append(
        {
            "stream": {
                "service": "http-to-mqtt-gateway",
                "level": "audit",
            },
            "values": values,
        }
    )

    payload: dict[str, Any] = {"streams": streams}

    try:
        with httpx.Client(timeout=_LOKI_TIMEOUT) as client:
            response = client.post(
                settings.LOKI_PUSH_URL,
                json=payload,
                auth=(
                    settings.LOKI_USERNAME,
                    settings.LOKI_PASSWORD,
                ),
            )
            response.raise_for_status()
    except Exception:
        logger.warning("loki push failed, dropping batch of %d entries", len(entries))


def _flush_batch() -> None:
    global _flush_timer
    with _batch_lock:
        if not _batch:
            _flush_timer = None
            return
        entries_to_send = list(_batch)
        _batch.clear()
        _flush_timer = None

    _push_to_loki(entries_to_send)


def _schedule_flush() -> None:
    global _flush_timer
    if _flush_timer is not None:
        return
    _flush_timer = threading.Timer(_FLUSH_INTERVAL, _flush_batch)
    _flush_timer.daemon = True
    _flush_timer.start()


def ship_entry(entry: dict[str, Any]) -> None:
    if not settings.GRAFANA_LOGGING_ENABLED:
        return
    global _flush_timer
    with _batch_lock:
        _batch.append(entry)
        if len(_batch) >= _BATCH_SIZE:
            entries_to_send = list(_batch)
            _batch.clear()
            if _flush_timer is not None:
                _flush_timer.cancel()
                _flush_timer = None
            _push_to_loki(entries_to_send)
        else:
            _schedule_flush()
