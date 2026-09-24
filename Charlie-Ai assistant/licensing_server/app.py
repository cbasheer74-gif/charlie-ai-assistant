"""
licensing_server/app.py — FastAPI application assembly with CORS, lifecycle, and route registration.

This is the AUTHORITATIVE licensing backend. The desktop app is NOT the authority for subscription state.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles

from licensing_server.config import config, ensure_rsa_keypair
from licensing_server.database import init_db
from licensing_server.routes import (
    account,
    admin,
    auth,
    device,
    entitlement,
    license,
    me,
    payment,
    portal,
    support,
    updates,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB tables + ensure RSA keypair exists."""
    init_db()
    ensure_rsa_keypair()
    print("[LICENSING SERVER] Database initialized. RSA keypair ready.")
    yield
    print("[LICENSING SERVER] Shutting down.")


app = FastAPI(
    title="JARVIS Licensing Server",
    description="Authoritative server for subscription management, device activation, signed entitlements, and payment verification.",
    version="1.0.0",
    lifespan=lifespan,
)

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Production browser security headers."""
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self';"
        )
        return response


from licensing_server.middleware.logging_middleware import StructuredLoggingMiddleware
from licensing_server.middleware.request_id_middleware import RequestIdMiddleware

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# Structured JSON Access Logging & Request ID Propagation
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(RequestIdMiddleware)

# CORS — restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if config.DEBUG else ["https://jarvis.app", "https://www.jarvis.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register routes
app.include_router(auth.router)
app.include_router(license.router)
app.include_router(entitlement.router)
app.include_router(device.router)
app.include_router(payment.router)
app.include_router(account.router)
app.include_router(me.router)
app.include_router(admin.router)
app.include_router(portal.router)
app.include_router(support.router)
app.include_router(updates.router)

# Mount downloads and site directory if available
downloads_dir = Path(__file__).resolve().parent.parent / "landing_page" / "downloads"
if downloads_dir.exists():
    app.mount("/downloads", StaticFiles(directory=str(downloads_dir)), name="downloads")

landing_page_dir = Path(__file__).resolve().parent.parent / "landing_page"
if landing_page_dir.exists():
    app.mount("/site", StaticFiles(directory=str(landing_page_dir), html=True), name="site")



import shutil
import time
from sqlalchemy import text
from licensing_server.database import engine

@app.get("/health")
def health(response: Response):
    """Deep healthcheck: verifies database connectivity, RSA keys, and storage."""
    start = time.perf_counter()
    db_healthy = False
    db_latency_ms = None
    db_error = None

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_latency_ms = round((time.perf_counter() - start) * 1000, 2)
        db_healthy = True
    except Exception as e:
        db_error = str(e)

    from licensing_server.config import PUBLIC_KEY_PATH, PRIVATE_KEY_PATH
    rsa_ready = PUBLIC_KEY_PATH.exists() and PRIVATE_KEY_PATH.exists()

    disk_free_gb = None
    try:
        usage = shutil.disk_usage(Path(__file__).resolve().parent)
        disk_free_gb = round(usage.free / (1024 ** 3), 2)
    except Exception:
        pass

    all_ok = db_healthy and rsa_ready
    if not all_ok:
        response.status_code = 503

    return {
        "status": "ok" if all_ok else "unhealthy",
        "service": "jarvis-licensing",
        "version": "1.0.0",
        "database": {
            "status": "connected" if db_healthy else "disconnected",
            "latency_ms": db_latency_ms,
            "error": db_error,
        },
        "security": {
            "rsa_keypair_ready": rsa_ready,
        },
        "system": {
            "disk_free_gb": disk_free_gb,
        },
    }


@app.get("/")
def root():
    return {
        "service": "JARVIS Licensing Server",
        "version": "1.0.0",
        "endpoints": [
            "POST /auth/register",
            "POST /auth/login",
            "POST /auth/refresh",
            "POST /license/activate",
            "POST /license/transfer",
            "POST /license/deactivate",
            "POST /license/revoke",
            "POST /entitlement/refresh",
            "GET  /entitlement/public-key",
            "GET  /devices/",
            "POST /payment/verify",
            "POST /payment/webhook",
            "GET  /account/",
        ],
    }
