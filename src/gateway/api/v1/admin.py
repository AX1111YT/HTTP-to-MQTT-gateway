from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.config import settings
from gateway.db.base import get_session
from gateway.db.models import Device, User
from gateway.rate_limit import limiter
from gateway.schemas.device import DeviceResponse
from gateway.schemas.user import (
    KeyRotateResponse,
    UserCreate,
    UserCreateResponse,
    UserResponse,
)
from gateway.audit import log_event
from gateway.security.deps import require_admin
from gateway.services import user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post(
    "/users", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit(settings.RATE_LIMIT_WRITE)
async def create_user(
    request: Request,
    body: UserCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin: Annotated[User, Depends(require_admin)],
) -> UserCreateResponse:
    user, raw_key = await user_service.create_user(session, body.display_name)
    log_event(
        request_id=request.state.request_id,
        actor_user_id=admin.id,
        actor_is_admin=admin.is_admin,
        action="create_user",
        target_type="user",
        target_id=user.id,
        result="success",
        source_ip=request.client.host if request.client else "unknown",
    )
    return UserCreateResponse(
        id=user.id,
        display_name=user.display_name,
        is_admin=user.is_admin,
        created_at=user.created_at,
        api_key=raw_key,
    )


@router.get("/users", response_model=list[UserResponse])
@limiter.limit(settings.RATE_LIMIT_READ)
async def list_users(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin: Annotated[User, Depends(require_admin)],
) -> list[User]:
    return await user_service.list_users(session)


@router.get("/users/{user_uuid}", response_model=UserResponse)
@limiter.limit(settings.RATE_LIMIT_READ)
async def get_user(
    request: Request,
    user_uuid: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin: Annotated[User, Depends(require_admin)],
) -> User:
    user = await user_service.get_user(session, user_uuid)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.delete("/users/{user_uuid}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.RATE_LIMIT_WRITE)
async def delete_user(
    request: Request,
    user_uuid: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin: Annotated[User, Depends(require_admin)],
) -> None:
    user = await user_service.get_user(session, user_uuid)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    await user_service.delete_user(session, user_uuid)
    log_event(
        request_id=request.state.request_id,
        actor_user_id=admin.id,
        actor_is_admin=admin.is_admin,
        action="delete_user",
        target_type="user",
        target_id=user_uuid,
        result="success",
        source_ip=request.client.host if request.client else "unknown",
    )


@router.post("/users/{user_uuid}/rotate-key", response_model=KeyRotateResponse)
@limiter.limit(settings.RATE_LIMIT_WRITE)
async def rotate_user_key(
    request: Request,
    user_uuid: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin: Annotated[User, Depends(require_admin)],
) -> dict[str, str]:
    try:
        _user, raw_key = await user_service.rotate_user_key(session, user_uuid)
    except ValueError:
        log_event(
            request_id=request.state.request_id,
            actor_user_id=admin.id,
            actor_is_admin=admin.is_admin,
            action="rotate_user_key",
            target_type="user",
            target_id=user_uuid,
            result="failure",
            source_ip=request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    log_event(
        request_id=request.state.request_id,
        actor_user_id=admin.id,
        actor_is_admin=admin.is_admin,
        action="rotate_user_key",
        target_type="user",
        target_id=user_uuid,
        result="success",
        source_ip=request.client.host if request.client else "unknown",
    )
    return {"api_key": raw_key}


@router.get("/devices", response_model=list[DeviceResponse])
@limiter.limit(settings.RATE_LIMIT_READ)
async def list_all_devices(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin: Annotated[User, Depends(require_admin)],
) -> Any:
    from sqlalchemy import select

    result = await session.execute(select(Device))
    return list(result.scalars().all())


@router.get("/audit-log")
@limiter.limit(settings.RATE_LIMIT_READ)
async def read_audit_log(
    request: Request,
    _admin: Annotated[User, Depends(require_admin)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> Any:
    from gateway.audit.writer import read_log_entries

    return read_log_entries(limit=limit)
