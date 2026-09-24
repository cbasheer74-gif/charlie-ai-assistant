"""
licensing_server/middleware/logging_middleware.py — Structured JSON HTTP request & error logging.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Configure dedicated structured logger
logger = logging.getLogger("licensing_server.access")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """
    Emits single-line machine-readable JSON log events for all incoming requests.
    Tracks latency (ms), request ID correlation, client IP, route, and status code.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()
        req_id = getattr(request.state, "request_id", request.headers.get("X-Request-ID", "unknown"))

        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "")[:120]
        method = request.method
        path = request.url.path

        try:
            response: Response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            status_code = response.status_code

            level = "INFO"
            if 400 <= status_code < 500:
                level = "WARN"
            elif status_code >= 500:
                level = "ERROR"

            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "service": "jarvis-licensing",
                "request_id": req_id,
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
                "user_agent": user_agent,
            }
            logger.info(json.dumps(log_entry))
            return response

        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "ERROR",
                "service": "jarvis-licensing",
                "request_id": req_id,
                "method": method,
                "path": path,
                "status_code": 500,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            logger.error(json.dumps(log_entry))
            raise exc
