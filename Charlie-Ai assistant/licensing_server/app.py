"""
licensing_server/app.py — FastAPI application assembly with CORS, lifecycle, and route registration.

This is the AUTHORITATIVE licensing backend. The desktop app is NOT the authority for subscription state.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from contextlib import asynccontextmanager

# Bootstrap sys.path for standalone or packaged execution
_server_dir = Path(__file__).resolve().parent
_repo_dir = _server_dir.parent
for _path_entry in (str(_server_dir), str(_repo_dir)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

SERVER_START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: setup log rotation, validate environment, init DB, and ensure RSA keypair."""
    from licensing_server.logging_config import setup_logging
    from licensing_server.env_validator import enforce_environment_or_halt

    setup_logging()
    enforce_environment_or_halt()
    init_db()
    ensure_rsa_keypair()
    print("[LICENSING SERVER] Logging initialized, config validated, DB ready, RSA keypair ready.")
    yield
    print("[LICENSING SERVER] Shutting down.")


app = FastAPI(
    title="CHARLIE AI Licensing Server",
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
            "connect-src 'self' http://localhost:* http://127.0.0.1:* https://charlie.ai https://api.razorpay.com;"
        )
        return response


from licensing_server.middleware.logging_middleware import StructuredLoggingMiddleware
from licensing_server.middleware.request_id_middleware import RequestIdMiddleware

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# Structured JSON Access Logging & Request ID Propagation
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(RequestIdMiddleware)

# Allowed Origins
DEV_ORIGINS = [
    "http://localhost:8400",
    "http://127.0.0.1:8400",
    "http://localhost:8500",
    "http://127.0.0.1:8500",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]
PROD_ORIGINS = [
    "https://charlie.ai",
    "https://www.charlie.ai",
    "https://charlie.app",
    "https://www.charlie.app",
]
CORS_ORIGINS = PROD_ORIGINS + DEV_ORIGINS if config.ENVIRONMENT != "production" else PROD_ORIGINS

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
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

admin_panel_dir = Path(__file__).resolve().parent.parent / "admin_panel"
if admin_panel_dir.exists():
    app.mount("/admin-panel", StaticFiles(directory=str(admin_panel_dir), html=True), name="admin_panel")


@app.get("/deployment-docs")
def direct_deployment_docs():
    from licensing_server.services.admin_service import AdminService
    return AdminService().get_deployment_docs()





import shutil
import time
from sqlalchemy import text
from licensing_server.database import engine

@app.get("/health")
def health(response: Response):
    """Deep healthcheck: verifies database connectivity, RSA keys, storage, uptime, and security subsystems."""
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
    disk_total_gb = None
    try:
        usage = shutil.disk_usage(Path(__file__).resolve().parent)
        disk_free_gb = round(usage.free / (1024 ** 3), 2)
        disk_total_gb = round(usage.total / (1024 ** 3), 2)
    except Exception:
        pass

    # Subsystem counters
    revoked_tokens = 0
    active_lockouts = 0
    try:
        from licensing_server.middleware.token_blacklist import token_blacklist
        revoked_tokens = token_blacklist.count()
    except Exception:
        pass

    try:
        from licensing_server.middleware.rate_limiter import get_active_lockouts
        active_lockouts = len(get_active_lockouts())
    except Exception:
        pass

    all_ok = db_healthy and rsa_ready
    if not all_ok:
        response.status_code = 503

    uptime_sec = int(time.time() - SERVER_START_TIME)

    return {
        "status": "ok" if all_ok else "unhealthy",
        "service": "charlie-licensing",
        "version": "1.0.0",
        "environment": config.ENVIRONMENT,
        "uptime_seconds": uptime_sec,
        "database": {
            "status": "connected" if db_healthy else "disconnected",
            "latency_ms": db_latency_ms,
            "error": db_error,
        },
        "security": {
            "rsa_keypair_ready": rsa_ready,
            "revoked_tokens_active": revoked_tokens,
            "account_lockouts_active": active_lockouts,
        },
        "system": {
            "disk_free_gb": disk_free_gb,
            "disk_total_gb": disk_total_gb,
        },
    }


@app.get("/")
def root():
    return {
        "service": "CHARLIE AI Licensing Server",
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
