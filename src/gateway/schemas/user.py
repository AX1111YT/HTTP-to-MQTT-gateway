from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UserCreate(BaseModel):
    display_name: str


class UserResponse(BaseModel):
    id: str
    display_name: str
    is_admin: bool
    created_at: datetime


class KeyRotateResponse(BaseModel):
    api_key: str


class UserCreateResponse(BaseModel):
    id: str
    display_name: str
    is_admin: bool
    created_at: datetime
    api_key: str
