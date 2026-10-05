# Environment Configuration Architecture

This document outlines the verified environment structure, environment variable handling, secrets management, and services for the CHARLIE system.

---

## 1. System Components & Architecture

The CHARLIE project consists of three distinct deployment domains:

1. **Desktop Client (`Charlie-Ai assistant/`)**: A PyInstaller + PyQt6 compiled Windows desktop application with offline fallback, Gemini Live integration, local SQLite data caches, and a background service agent.
2. **Commercial Licensing & Control Server (`Charlie-Ai assistant/licensing_server/`)**: A FastAPI + SQLAlchemy server that manages customer identities, hardware node locks (fingerprints), Razorpay payments, subscriptions, remote configuration, crash telemetry, and signed updates.
3. **Admin Web Control Center (`Charlie-Ai assistant/admin_panel/`)**: A client-side vanilla JavaScript/CSS single-page application served via static files by the licensing server at `/admin-panel/`.

---

## 2. Environment Profiles

The project differentiates environments primarily via the `CHARLIE_ENV` variable:

| Parameter | Development | Staging (Pre-Release) | Production |
| :--- | :--- | :--- | :--- |
| `CHARLIE_ENV` | `development` (or unset) | `staging` / `beta` | `production` |
| **Server Host & Port** | `127.0.0.1:8400` | `0.0.0.0:8400` | Configured via reverse proxy / cloud VM |
| **Admin Key Fallback** | Hardcoded default allowed (`charlie_admin_secret_key_2026`) | Must be overridden | **Forced override required**; defaults to empty string if unset |
| **JWT Secret Fallback** | `charlie_jwt_dev_secret_change_in_production` | Must be overridden | Must be overridden via environment |
| **Database** | Local SQLite (`charlie_licensing.db`) | SQLite or remote DB URL | `CHARLIE_DB_URL` (SQLite or PostgreSQL) |
| **Debug Flag** | Optional (`CHARLIE_DEBUG=true`) | `false` | `false` |
| **Client Release Channel** | `INTERNAL` / `DEV` | `BETA` | `STABLE` |

---

## 3. Environment Variables Reference

All verified environment variables read by the server and client codebase:

### Core Server & Security

| Variable | Default (Dev) | Description | Verified Source |
| :--- | :--- | :--- | :--- |
| `CHARLIE_ENV` | `development` | Environment mode (`development`, `staging`, `production`) | `licensing_server/config.py` |
| `CHARLIE_SERVER_HOST` | `0.0.0.0` | Host address to bind FastAPI server | `licensing_server/config.py` |
| `CHARLIE_SERVER_PORT` | `8400` | Port for licensing and admin server | `licensing_server/config.py` |
| `CHARLIE_DEBUG` | `false` | Enables verbose debug logging | `licensing_server/config.py` |
| `CHARLIE_ADMIN_KEY` | `charlie_admin_secret_key_2026` (dev only) | Secret API key for administrative operations (`X-Admin-Key`) | `licensing_server/config.py` |
| `CHARLIE_JWT_SECRET` | `charlie_jwt_dev_secret_...` | HMAC secret key used to sign access/refresh tokens | `licensing_server/config.py` |
| `CHARLIE_JWT_ACCESS_EXPIRY` | `60` | JWT Access Token lifetime in minutes | `licensing_server/config.py` |
| `CHARLIE_JWT_REFRESH_EXPIRY` | `30` | JWT Refresh Token lifetime in days | `licensing_server/config.py` |
| `CHARLIE_DB_URL` | `sqlite:///charlie_licensing.db` | SQLAlchemy database connection string | `licensing_server/config.py` |
| `CHARLIE_PRODUCT_SALT` | `charlie_ai_2026` | Salt used in client device fingerprint hashing | `licensing_server/config.py` |
| `ENTITLEMENT_SIGNING_KEY_PEM` | Unset (uses file `keys/entitlement_signing.pem`) | RSA-2048 private key string for signing license entitlements | `licensing_server/config.py` |

### Payment Gateway (Razorpay)

| Variable | Default | Description | Verified Source |
| :--- | :--- | :--- | :--- |
| `RAZORPAY_KEY_ID` | `""` | Razorpay public key ID (`rzp_test_...` or `rzp_live_...`) | `licensing_server/config.py` |
| `RAZORPAY_KEY_SECRET` | `""` | Razorpay API private secret | `licensing_server/config.py` |
| `RAZORPAY_WEBHOOK_SECRET` | `""` | Secret to validate incoming Razorpay webhook signatures | `licensing_server/config.py` |

### Email Delivery (SMTP)

| Variable | Default | Description | Verified Source |
| :--- | :--- | :--- | :--- |
| `CHARLIE_SMTP_HOST` / `SMTP_HOST` | `""` | Outbound mail server hostname | `licensing_server/config.py` |
| `CHARLIE_SMTP_PORT` / `SMTP_PORT` | `587` | Outbound mail server port | `licensing_server/config.py` |
| `CHARLIE_SMTP_USER` / `SMTP_USER` | `""` | SMTP authentication username | `licensing_server/config.py` |
| `CHARLIE_SMTP_PASSWORD` / `SMTP_PASSWORD` | `""` | SMTP authentication password | `licensing_server/config.py` |
| `CHARLIE_SMTP_FROM` / `SMTP_FROM` | `noreply@charlie.ai` | From address for transactional notification emails | `licensing_server/config.py` |
| `CHARLIE_SMTP_TLS` | `true` | Enforces STARTTLS during SMTP handshake | `licensing_server/config.py` |

### Rate Limits & Client Policies

| Variable | Default | Description | Verified Source |
| :--- | :--- | :--- | :--- |
| `CHARLIE_LOGIN_RATE_LIMIT` | `10` | Max login attempts per minute per IP | `licensing_server/config.py` |
| `CHARLIE_ACTIVATION_RATE_LIMIT` | `5` | Max hardware device activation calls per minute | `licensing_server/config.py` |
| `CHARLIE_TRANSFER_RATE_LIMIT` | `3` | Max license re-bind attempts per hour | `licensing_server/config.py` |
| `CHARLIE_MAX_TRANSFERS_MONTH` | `3` | Maximum allowed license transfers per user per calendar month | `licensing_server/config.py` |
| `CHARLIE_MONTHLY_OFFLINE_DAYS` | `14` | Offline grace period before monthly plan requires server re-validation | `licensing_server/config.py` |
| `CHARLIE_LIFETIME_OFFLINE_DAYS` | `90` | Offline grace period before lifetime license requires check-in | `licensing_server/config.py` |

### Desktop Client Runtime (`api_keys.json` / Local Config)

| Variable / Key | Location | Purpose |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | `config/api_keys.json` or Environment | Google Gemini Live multimodal inference |
| `OPENAI_API_KEY` | `config/api_keys.json` or Environment | Optional fallback LLM provider |
| `GROQ_API_KEY` | `config/api_keys.json` or Environment | Fast LPU Llama-3 inference |
| `PICOVOICE_API_KEY` | `config/api_keys.json` or Environment | Offline Porcupine wake word engine |

---

## 4. Secrets Handling & Verification

### Verified Implementations

1. **Pre-build Secret Scanner (`build_production.py`)**: Automatically scans source files before packaging. Blocks build execution if Google, OpenAI, Razorpay, or raw private keys are found in distribution paths.
2. **Public Key Embedding**: The client verifier (`entitlement_verifier.py`) contains only the RSA-2048 public key. The private key (`entitlement_signing.pem`) is restricted to the licensing server.
3. **Support Ticket & Crash Log Redactor (`SecretRedactor`)**: All incoming client diagnostics, logs, and stack traces pass through an automated redaction regex parser before database insertion.

### Gaps & Unknowns

- **UNKNOWN / NEEDS CONFIRMATION**: Production cloud secrets manager integration (e.g., AWS Secrets Manager, HashiCorp Vault, Azure Key Vault). Currently, secrets rely entirely on OS environment variables or local `.env` files.
- **UNKNOWN / NEEDS CONFIRMATION**: Production reverse proxy SSL certificate lifecycle (e.g. Certbot/Let's Encrypt for `https://updates.charlie.ai`).
