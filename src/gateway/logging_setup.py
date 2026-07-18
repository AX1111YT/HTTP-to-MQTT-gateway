from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from io import TextIOWrapper
from pathlib import Path
from typing import Any

LOG_DIR = Path("/logs")
MAX_BYTES = 128 * 1024


class JSONLHandler(logging.Handler):
    def __init__(self, log_dir: Path = LOG_DIR, max_bytes: int = MAX_BYTES) -> None:
        super().__init__()
        self._log_dir = log_dir
        self._max_bytes = max_bytes
        self._current_day: str = ""
        self._file_no: int = 0
        self._current_size: int = 0
        self._stream: TextIOWrapper | None = None
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._open_new_file(datetime.now(timezone.utc).strftime("%Y-%m-%d"), 0)

    def _open_new_file(self, day: str, file_no: int) -> None:
        if self._stream is not None:
            self._stream.close()
        self._current_day = day
        self._file_no = file_no
        self._current_size = 0
        path = self._log_dir / f"{day}-{file_no:04d}.log"
        self._stream = open(path, "a", encoding="utf-8")
        self._current_size = path.stat().st_size if path.exists() else 0

    def _rotate_if_needed(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._current_day:
            self._open_new_file(today, 0)
            return
        if self._current_size >= self._max_bytes:
            self._open_new_file(self._current_day, self._file_no + 1)

    def emit(self, record: logging.LogRecord) -> None:
        self._rotate_if_needed()
        if self._stream is None:
            return
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1] is not None:
            entry["exc"] = logging.Formatter().formatException(record.exc_info)
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        self._stream.write(line)
        self._stream.flush()
        self._current_size += len(line.encode("utf-8"))

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
        super().close()


def setup_logging(level: str = "INFO") -> None:
    handler = JSONLHandler()
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(handler)
