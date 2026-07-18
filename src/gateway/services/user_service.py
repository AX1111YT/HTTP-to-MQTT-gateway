from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.db.models import User
from gateway.security.api_keys import (
    generate_api_key,
    hash_api_key,
    compute_lookup_hash,
)

logger = logging.getLogger(__name__)


async def create_user(
    session: AsyncSession, display_name: str, is_admin: bool = False
) -> tuple[User, str]:
    raw_key = generate_api_key()
    user = User(
        display_name=display_name,
        api_key_hash=hash_api_key(raw_key),
        api_key_lookup_hash=compute_lookup_hash(raw_key),
        is_admin=is_admin,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info("created user %s", user.id)
    return user, raw_key


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User))
    return list(result.scalars().all())


async def get_user(session: AsyncSession, user_id: str) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def delete_user(session: AsyncSession, user_id: str) -> None:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return
    await session.delete(user)
    await session.commit()
    logger.info("deleted user %s", user_id)


async def rotate_user_key(session: AsyncSession, user_id: str) -> tuple[User, str]:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError(f"User {user_id} not found")

    from datetime import datetime, timezone

    raw_key = generate_api_key()
    user.api_key_hash = hash_api_key(raw_key)
    user.api_key_lookup_hash = compute_lookup_hash(raw_key)
    user.key_rotated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(user)
    logger.info("rotated key for user %s", user_id)
    return user, raw_key
