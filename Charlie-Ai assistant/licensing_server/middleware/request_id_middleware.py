"""
licensing_server/middleware/request_id_middleware.py — Request ID extraction, generation, and propagation.
"""

from __future__ import annotations

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Ensures every request has a unique Request ID.
    Reads X-Request-ID if provided by client/proxy, otherwise generates one.
    Attaches it to request.state.request_id and response headers.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = request.headers.get("X-Request-ID")
        if not req_id or len(req_id) > 64:
            req_id = f"req_{uuid.uuid4().hex[:16]}"

        request.state.request_id = req_id
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response
