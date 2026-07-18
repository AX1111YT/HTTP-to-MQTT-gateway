from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SwitchCommand(BaseModel):
    state: str = Field(pattern=r"^(ON|OFF)$")


class LightCommand(BaseModel):
    state: str = Field(pattern=r"^(ON|OFF)$")
    brightness: int | None = Field(default=None, ge=0, le=255)


class SensorCommand(BaseModel):
    value: float


class BinarySensorCommand(BaseModel):
    pass


class ClimateCommand(BaseModel):
    mode: str | None = Field(default=None, pattern=r"^(off|heat|cool|heat_cool|auto)$")
    target_temp: float | None = Field(default=None, ge=0, le=100)


class NumberCommand(BaseModel):
    value: float


class FanCommand(BaseModel):
    state: str = Field(pattern=r"^(ON|OFF)$")
    speed: int | None = Field(default=None, ge=0, le=100)


class LockCommand(BaseModel):
    state: str = Field(pattern=r"^(LOCK|UNLOCK)$")


class CoverCommand(BaseModel):
    state: str = Field(pattern=r"^(OPEN|CLOSE|STOP)$")


class CommandRequest(BaseModel):
    payload: dict[str, Any]
