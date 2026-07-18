from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gateway.logging_setup import JSONLHandler

_AUDIT_LOG_DIR = Path("/logs/audit")
_AUDIT_LOGGER_NAME = "gateway.audit"

_logger = logging.getLogger(_AUDIT_LOGGER_NAME)
_initialized = False


def _ensure_initialized() -> None:
    global _initialized
    if _initialized:
        return
    handler = JSONLHandler(log_dir=_AUDIT_LOG_DIR)
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False
    _initialized = True


def log_event(
    *,
    request_id: str,
    actor_user_id: str,
    actor_is_admin: bool,
    action: str,
    target_type: str,
    target_id: str,
    result: str,
    source_ip: str,
) -> None:
    _ensure_initialized()
    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "actor_user_id": actor_user_id,
        "actor_is_admin": actor_is_admin,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "result": result,
        "source_ip": source_ip,
    }
    _logger.info(json.dumps(entry, ensure_ascii=False))

    from gateway.config import settings

    if settings.GRAFANA_LOGGING_ENABLED:
        from gateway.audit.loki_shipper import ship_entry

        ship_entry(entry)


def read_log_entries(
    *,
    actor_or_target_user_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if not _AUDIT_LOG_DIR.exists():
        return []

    entries: list[dict[str, Any]] = []
    for log_file in sorted(_AUDIT_LOG_DIR.glob("*.log"), reverse=True):
        with log_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                message = record.get("message", "")
                try:
                    entry = json.loads(message)
                except json.JSONDecodeError, TypeError:
                    continue
                if actor_or_target_user_id is not None:
                    is_actor = entry.get("actor_user_id") == actor_or_target_user_id
                    is_target = (
                        entry.get("target_type") == "user"
                        and entry.get("target_id") == actor_or_target_user_id
                    )
                    if not (is_actor or is_target):
                        continue
                entries.append(entry)

    return entries[-limit:]
