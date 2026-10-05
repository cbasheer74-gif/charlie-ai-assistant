# Deployment & Operational Architecture

This document specifies the verified deployment procedures for both the commercial licensing control backend and the desktop client fleet.

---

## 1. Deployment Architecture

```text
                       ┌────────────────────────────────────────────────────────┐
                       │                   PUBLIC CLIENT FLEET                  │
                       │           (Windows 10 / 11 Desktop Machines)           │
                       └───────────────────────────┬────────────────────────────┘
                                                   │
                            HTTPS REST / JSON (TLS 1.2/1.3)
                            - Device Activation & Refresh (/api/devices/*)
                            - Signed Update Polling (/updates/check)
                            - Diagnostic Logs & Crash Telemetry (/api/support/tickets)
                                                   │
                                                   ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────┐
│                           COMMERCIAL CONTROL SERVER (FastAPI + Uvicorn)                       │
│                                                                                               │
│  [Reverse Proxy: Nginx / Cloudflare (Port 443)] ──► [Uvicorn ASGI App (Port 8400)]             │
│                                                                                               │
│  Subsystems:                                                                                  │
│   ├── Licensing Engine (/api/license/*)                                                       │
│   ├── User & Entitlement Authority (/api/users/*)                                             │
│   ├── Payment & Webhook Verification (/api/payments/*)                                        │
│   ├── Signed Release Management (/updates/releases)                                           │
│   ├── Support & Redacted Diagnostics (/api/support/*)                                         │
│   └── Admin Control Web Center (/admin-panel/)                                                │
│                                                                                               │
│  Database Layer:                                                                              │
│   └── SQLite / PostgreSQL via SQLAlchemy (`charlie_licensing.db`)                              │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Server Deployment Prerequisites

1. **Python Runtime**: Python 3.10, 3.11, or 3.12 (64-bit).
2. **Reverse Proxy / SSL**: Nginx, Caddy, or Cloudflare with TLS termination.
3. **Persistent Volume**: Directory for SQLite DB (`charlie_licensing.db`) or a connection string to a managed PostgreSQL cluster (`CHARLIE_DB_URL`).
4. **RSA Key Storage**: Secure storage directory `licensing_server/keys/` for `entitlement_signing.pem` and `entitlement_verify.pub`.

---

## 3. Server Deployment Steps (Production)

### Step 1: Environment Provisioning

Export mandatory production environment variables:

```bash
export CHARLIE_ENV="production"
export CHARLIE_ADMIN_KEY="<STRONG_RANDOM_UUID_OR_SECRET>"
export CHARLIE_JWT_SECRET="<SECURE_256BIT_SECRET>"
export CHARLIE_SERVER_HOST="127.0.0.1"
export CHARLIE_SERVER_PORT="8400"
export RAZORPAY_KEY_ID="rzp_live_..."
export RAZORPAY_KEY_SECRET="<LIVE_PAYMENT_SECRET>"
export RAZORPAY_WEBHOOK_SECRET="<LIVE_WEBHOOK_SECRET>"
export CHARLIE_DB_URL="sqlite:///./charlie_licensing.db"
```

### Step 2: Database Initialization & Migration

Execute database schema initialization:

```python
python -c "from licensing_server.database import init_db; init_db()"
```

*Note*: `init_db()` runs automatic non-destructive column additions via SQLite `PRAGMA table_info` and `ALTER TABLE ADD COLUMN`.

### Step 3: Server Process Startup

#### Local / Dedicated Host (Windows)

```bat
run_admin_panel.bat
```

*(Runs uvicorn at `http://localhost:8400/admin-panel/` and opens default browser)*

#### Linux / Systemd Service Execution

```bash
uvicorn licensing_server.app:app --host 127.0.0.1 --port 8400 --workers 4
```

---

## 4. Desktop Client Update Deployment

Official client binary releases are distributed through the Server's staged update engine:

### Step 1: Generate Release Package

Run `build_production.py` to create `CHARLIE-Setup-<version>.exe`.

### Step 2: Calculate Cryptographic Hash

```powershell
CertUtil -hashfile dist\CHARLIE-Setup-1.3.0.exe SHA256
```

### Step 3: Register Release on Update Server

Register the release to the `BETA` channel:

```http
POST /updates/releases
Host: licensing.charlie.ai
X-Admin-Key: <ADMIN_KEY>
Content-Type: application/json

{
  "version": "1.3.0",
  "build_number": 130,
  "channel": "BETA",
  "download_url": "https://updates.charlie.ai/v1.3.0/CHARLIE-Setup-1.3.0.exe",
  "sha256": "<COMPUTED_SHA256_HEX>",
  "release_notes": "Official release notes for version 1.3.0",
  "mandatory": false,
  "rollback_supported": true
}
```

### Step 4: Staged Rollout Execution

Once verified by beta testers, promote to `STABLE` with staged percentages:

1. **5% Canary Cohort**: `POST /updates/releases/1.3.0/rollout` -> `{"rollout_percentage": 5}`
2. **25% Cohort**: `POST /updates/releases/1.3.0/rollout` -> `{"rollout_percentage": 25}`
3. **50% Cohort**: `POST /updates/releases/1.3.0/rollout` -> `{"rollout_percentage": 50}`
4. **100% Full GA**: `POST /updates/releases/1.3.0/rollout` -> `{"rollout_percentage": 100}`

---

## 5. Health Verification & Smoke Tests

### Health Endpoints

- **Server Readiness**: `GET /health` → Returns HTTP 200 `{"status": "healthy"}`.
- **Admin Authentication**: `GET /admin/api/profile` with header `X-Admin-Key`.
- **KPI Metrics Endpoint**: `GET /admin/api/metrics`.
- **Client Update Probe**: `POST /updates/check` with payload `{"current_version": "1.2.2", "os": "Windows"}`.

### Desktop Health Check Tool

Run `check_health.py` on the client host:

```powershell
python check_health.py
```

Validates Python runtime, core PyQt6 modules, sounddevice microphones, audio outputs, and local directory locks.

---

## 6. Common Deployment Failure Points

1. **Missing RSA Public Key**: If `build_production.py` runs before `licensing_server/keys/entitlement_verify.pub` exists, client entitlement verification will fail with `NO_PUBLIC_KEY_CONFIGURED`.
2. **Missing Admin API Key**: In `production` mode, `CHARLIE_ADMIN_KEY` defaults to empty string if unset; all admin endpoints will reject access with HTTP 403.
3. **Single-Instance Lock Collision**: If an old process terminates abnormally, `charlie.lock` may remain in `{user_data}/checkpoints/`. `SingleInstanceManager` validates the PID before failing, but file permission locks can block startup.
4. **Inno Setup Missing**: If Inno Setup is not installed in standard 32-bit/64-bit Program Files directories, `build_production.py` will skip installer generation.
