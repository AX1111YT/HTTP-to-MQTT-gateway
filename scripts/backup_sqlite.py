from __future__ import annotations

import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from b2sdk.v2 import B2Api, InMemoryAccountInfo  # type: ignore[import-untyped]
from cryptography.fernet import Fernet

from gateway.audit.writer import log_event
from gateway.config import settings

BACKUP_DIR = Path(tempfile.gettempdir()) / "gateway-backups"


def _extract_db_path(database_url: str) -> Path:
    parsed = urlparse(database_url)
    raw = parsed.path or parsed.netloc
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _vacuum_into(source_db: Path, dest: Path) -> None:
    conn = sqlite3.connect(str(source_db))
    try:
        conn.execute(f"VACUUM INTO '{dest}'")
    finally:
        conn.close()


def _encrypt_file(src: Path, key: bytes) -> Path:
    fernet = Fernet(key)
    encrypted = src.with_suffix(src.suffix + ".enc")
    data = src.read_bytes()
    encrypted.write_bytes(fernet.encrypt(data))
    return encrypted


def _upload_to_b2(
    file_path: Path,
    bucket_name: str,
    key_id: str,
    app_key: str,
    endpoint_url: str,
) -> str:
    info = InMemoryAccountInfo()
    api = B2Api(info)
    api.authorize_account(
        realm="b2",
        application_key_id=key_id,
        application_key=app_key,
    )
    bucket = api.get_bucket_by_name(bucket_name)
    b2_path = f"backups/{file_path.name}"
    uploaded = bucket.upload_local_file(
        local_file=str(file_path),
        file_name=b2_path,
    )
    return str(uploaded.id_)


def _cleanup(*paths: Path) -> None:
    for p in paths:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def main() -> None:
    if not settings.BACKUP_ENABLED:
        print("backup disabled (BACKUP_ENABLED=False), skipping")
        return

    db_path = _extract_db_path(settings.DATABASE_URL)
    if not db_path.exists():
        print(f"database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    snapshot = BACKUP_DIR / f"gateway-{timestamp}.db"
    encrypted: Path | None = None

    try:
        # consistent point-in-time snapshot
        _vacuum_into(db_path, snapshot)
        print(f"snapshot created: {snapshot}")

        # encrypt before upload
        key = settings.BACKUP_ENCRYPTION_KEY.encode()
        encrypted = _encrypt_file(snapshot, key)
        print(f"encrypted: {encrypted}")

        # upload to B2
        file_id = _upload_to_b2(
            encrypted,
            settings.B2_BUCKET_NAME,
            settings.B2_APPLICATION_KEY_ID,
            settings.B2_APPLICATION_KEY,
            settings.B2_ENDPOINT_URL,
        )
        print(f"uploaded, file_id={file_id}")

        log_event(
            request_id="backup",
            actor_user_id="system",
            actor_is_admin=True,
            action="backup.uploaded",
            target_type="backup",
            target_id=file_id,
            result="success",
            source_ip="localhost",
        )

    except Exception as exc:
        print(f"backup failed: {exc}", file=sys.stderr)
        log_event(
            request_id="backup",
            actor_user_id="system",
            actor_is_admin=True,
            action="backup.failed",
            target_type="backup",
            target_id=str(db_path),
            result=f"error: {exc}",
            source_ip="localhost",
        )
        sys.exit(1)

    finally:
        _cleanup(snapshot, encrypted) if encrypted else _cleanup(snapshot)


if __name__ == "__main__":
    main()
