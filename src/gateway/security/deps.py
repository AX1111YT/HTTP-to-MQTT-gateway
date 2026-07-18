from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.db.base import get_session
from gateway.db.models import User
from gateway.security.api_keys import compute_lookup_hash, verify_api_key

logger = logging.getLogger(__name__)

AUTH_SCHEME = "Bearer"


async def _extract_api_key(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    parts = auth_header.split()
    if len(parts) != 2 or parts[0] != AUTH_SCHEME:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
        )
    return parts[1]


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    raw_key = await _extract_api_key(request)
    lookup_hash = compute_lookup_hash(raw_key)
    result = await session.execute(
        select(User).where(User.api_key_lookup_hash == lookup_hash)
    )
    user = result.scalars().first()
    if user is not None and verify_api_key(raw_key, user.api_key_hash):
        request.state.user = user
        return user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )


async def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def require_ownership_or_admin(
    user_uuid: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if current_user.is_admin or current_user.id == user_uuid:
        return current_user
    # 404, not 403 — never confirm existence to unauthorized callers
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="User not found",
    )
