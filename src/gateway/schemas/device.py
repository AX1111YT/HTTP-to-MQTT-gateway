from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DeviceCreate(BaseModel):
    name: str


class DeviceResponse(BaseModel):
    id: str
    name: str
    topic_prefix: str
    mqtt_username: str
    created_at: datetime
    last_seen_at: datetime | None
    online: bool


class DeviceCreateResponse(DeviceResponse):
    mqtt_password: str


class DeviceUpdate(BaseModel):
    name: str
