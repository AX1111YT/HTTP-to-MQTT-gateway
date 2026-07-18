from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.config import settings
from gateway.db.base import get_session
from gateway.db.models import Device, User
from gateway.mqtt.client import mqtt_client
from gateway.rate_limit import limiter
from gateway.schemas.device import (
    DeviceCreate,
    DeviceCreateResponse,
    DeviceResponse,
    DeviceUpdate,
)
from gateway.schemas.command import CommandRequest
from gateway.schemas.user import KeyRotateResponse, UserResponse
from gateway.audit import log_event
from gateway.security.deps import require_ownership_or_admin
from gateway.services import command_service, device_service, user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/{user_uuid}", response_model=UserResponse)
@limiter.limit(settings.RATE_LIMIT_READ)
async def get_self(
    request: Request,
    user_uuid: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_ownership_or_admin)],
) -> User:
    user = await user_service.get_user(session, user_uuid)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.post("/{user_uuid}/rotate-key", response_model=KeyRotateResponse)
@limiter.limit(settings.RATE_LIMIT_WRITE)
async def rotate_own_key(
    request: Request,
    user_uuid: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_ownership_or_admin)],
) -> dict[str, str]:
    _user, raw_key = await user_service.rotate_user_key(session, user_uuid)
    return {"api_key": raw_key}


@router.get("/{user_uuid}/devices", response_model=list[DeviceResponse])
@limiter.limit(settings.RATE_LIMIT_READ)
async def list_devices(
    request: Request,
    user_uuid: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_ownership_or_admin)],
) -> list[Device]:
    return await device_service.list_devices(session, user_uuid)


@router.post(
    "/{user_uuid}/devices",
    response_model=DeviceCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(settings.RATE_LIMIT_WRITE)
async def create_device(
    request: Request,
    user_uuid: str,
    body: DeviceCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_ownership_or_admin)],
) -> Any:
    try:
        device, mqtt_password = await device_service.create_device(
            session,
            mqtt_client,
            user_uuid,
            body.name,
            bypass_limit=current_user.is_admin,
        )
    except device_service.DeviceLimitExceededError as exc:
        log_event(
            request_id=request.state.request_id,
            actor_user_id=current_user.id,
            actor_is_admin=current_user.is_admin,
            action="create_device",
            target_type="device",
            target_id="",
            result="failure",
            source_ip=request.client.host if request.client else "unknown",
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError:
        log_event(
            request_id=request.state.request_id,
            actor_user_id=current_user.id,
            actor_is_admin=current_user.is_admin,
            action="create_device",
            target_type="device",
            target_id="",
            result="failure",
            source_ip=request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    log_event(
        request_id=request.state.request_id,
        actor_user_id=current_user.id,
        actor_is_admin=current_user.is_admin,
        action="create_device",
        target_type="device",
        target_id=device.id,
        result="success",
        source_ip=request.client.host if request.client else "unknown",
    )
    return DeviceCreateResponse(
        id=device.id,
        name=device.name,
        topic_prefix=device.topic_prefix,
        mqtt_username=device.mqtt_username,
        created_at=device.created_at,
        last_seen_at=device.last_seen_at,
        online=device.online,
        mqtt_password=mqtt_password,
    )


@router.get("/{user_uuid}/devices/{device_id}", response_model=DeviceResponse)
@limiter.limit(settings.RATE_LIMIT_READ)
async def get_device(
    request: Request,
    user_uuid: str,
    device_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_ownership_or_admin)],
) -> Device:
    device = await device_service.get_device(session, device_id)
    if device is None or device.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not found"
        )
    return device


@router.patch("/{user_uuid}/devices/{device_id}", response_model=DeviceResponse)
@limiter.limit(settings.RATE_LIMIT_WRITE)
async def update_device(
    request: Request,
    user_uuid: str,
    device_id: str,
    body: DeviceUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_ownership_or_admin)],
) -> Device:
    device = await device_service.get_device(session, device_id)
    if device is None or device.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not found"
        )
    try:
        updated = await device_service.update_device(session, device_id, body.name)
    except ValueError:
        log_event(
            request_id=request.state.request_id,
            actor_user_id=current_user.id,
            actor_is_admin=current_user.is_admin,
            action="update_device",
            target_type="device",
            target_id=device_id,
            result="failure",
            source_ip=request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not found"
        )
    log_event(
        request_id=request.state.request_id,
        actor_user_id=current_user.id,
        actor_is_admin=current_user.is_admin,
        action="update_device",
        target_type="device",
        target_id=device_id,
        result="success",
        source_ip=request.client.host if request.client else "unknown",
    )
    return updated


@router.delete(
    "/{user_uuid}/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT
)
@limiter.limit(settings.RATE_LIMIT_WRITE)
async def delete_device(
    request: Request,
    user_uuid: str,
    device_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_ownership_or_admin)],
) -> None:
    device = await device_service.get_device(session, device_id)
    if device is None or device.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not found"
        )
    await device_service.delete_device(session, mqtt_client, device_id)
    log_event(
        request_id=request.state.request_id,
        actor_user_id=current_user.id,
        actor_is_admin=current_user.is_admin,
        action="delete_device",
        target_type="device",
        target_id=device_id,
        result="success",
        source_ip=request.client.host if request.client else "unknown",
    )


@router.get(
    "/{user_uuid}/devices/{device_id}/entities",
    response_model=list[dict[str, Any]],
)
@limiter.limit(settings.RATE_LIMIT_READ)
async def list_entities(
    request: Request,
    user_uuid: str,
    device_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_ownership_or_admin)],
) -> Any:
    device = await device_service.get_device(session, device_id)
    if device is None or device.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not found"
        )
    entities = await device_service.list_entities(session, device_id)
    return [
        {
            "id": e.id,
            "component_type": e.component_type,
            "object_id": e.object_id,
            "friendly_name": e.friendly_name,
            "unit": e.unit,
            "device_class": e.device_class,
            "state_topic": e.state_topic,
            "command_topic": e.command_topic,
            "current_value": e.current_value,
            "last_updated_at": e.last_updated_at,
        }
        for e in entities
    ]


@router.get(
    "/{user_uuid}/devices/{device_id}/entities/{entity_id}",
    response_model=dict[str, Any],
)
@limiter.limit(settings.RATE_LIMIT_READ)
async def get_entity(
    request: Request,
    user_uuid: str,
    device_id: str,
    entity_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_ownership_or_admin)],
) -> dict[str, Any]:
    device = await device_service.get_device(session, device_id)
    if device is None or device.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not found"
        )
    entity = await device_service.get_entity(session, entity_id)
    if entity is None or entity.device_id != device_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found"
        )
    return {
        "id": entity.id,
        "component_type": entity.component_type,
        "object_id": entity.object_id,
        "friendly_name": entity.friendly_name,
        "unit": entity.unit,
        "device_class": entity.device_class,
        "state_topic": entity.state_topic,
        "command_topic": entity.command_topic,
        "current_value": entity.current_value,
        "last_updated_at": entity.last_updated_at,
    }


@router.post(
    "/{user_uuid}/devices/{device_id}/entities/{entity_id}/command",
    status_code=status.HTTP_200_OK,
)
@limiter.limit(settings.RATE_LIMIT_WRITE)
async def send_command(
    request: Request,
    user_uuid: str,
    device_id: str,
    entity_id: str,
    body: CommandRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_ownership_or_admin)],
) -> dict[str, str]:
    device = await device_service.get_device(session, device_id)
    if device is None or device.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not found"
        )
    entity = await device_service.get_entity(session, entity_id)
    if entity is None or entity.device_id != device_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found"
        )
    try:
        await command_service.send_command(mqtt_client, device, entity, body.payload)
    except ValueError as exc:
        log_event(
            request_id=request.state.request_id,
            actor_user_id=current_user.id,
            actor_is_admin=current_user.is_admin,
            action="send_command",
            target_type="entity",
            target_id=entity_id,
            result="failure",
            source_ip=request.client.host if request.client else "unknown",
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    log_event(
        request_id=request.state.request_id,
        actor_user_id=current_user.id,
        actor_is_admin=current_user.is_admin,
        action="send_command",
        target_type="entity",
        target_id=entity_id,
        result="success",
        source_ip=request.client.host if request.client else "unknown",
    )
    return {"status": "ok"}


@router.get("/{user_uuid}/audit-log")
@limiter.limit(settings.RATE_LIMIT_READ)
async def read_own_audit_log(
    request: Request,
    user_uuid: str,
    current_user: Annotated[User, Depends(require_ownership_or_admin)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> Any:
    from gateway.audit.writer import read_log_entries

    return read_log_entries(actor_or_target_user_id=user_uuid, limit=limit)
