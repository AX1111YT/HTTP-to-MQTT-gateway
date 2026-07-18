from __future__ import annotations

import asyncio
import os
import secrets

import argon2
from sqlalchemy import select

from gateway.db.base import async_session_factory
from gateway.db.models import User
from gateway.security.api_keys import compute_lookup_hash


async def main() -> None:
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.is_admin.is_(True)))
        if result.scalars().first() is not None:
            print("Admin already exists, skipping creation.")
            return

    plaintext_key = os.environ.get("ADMIN_API_KEY") or secrets.token_urlsafe(32)
    hasher = argon2.PasswordHasher()
    key_hash = hasher.hash(plaintext_key)
    lookup_hash = compute_lookup_hash(plaintext_key)

    async with async_session_factory() as session:
        admin = User(
            display_name="Admin",
            api_key_hash=key_hash,
            api_key_lookup_hash=lookup_hash,
            is_admin=True,
        )
        session.add(admin)
        await session.commit()

    print(f"Admin API key (shown once, store it securely): {plaintext_key}")


if __name__ == "__main__":
    asyncio.run(main())
