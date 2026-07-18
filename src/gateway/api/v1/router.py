from __future__ import annotations

from fastapi import APIRouter

from gateway.api.v1.admin import router as admin_router
from gateway.api.v1.system import router as system_router
from gateway.api.v1.user import router as user_router

api_router = APIRouter()
api_router.include_router(system_router)
api_router.include_router(admin_router)
api_router.include_router(user_router)
