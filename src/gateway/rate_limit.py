from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request as StarletteRequest


def api_key_func(request: StarletteRequest) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return get_remote_address(request)


limiter = Limiter(key_func=api_key_func)
