# 06 — API Test Plan

Target: FastAPI Licensing Server Routes (`licensing_server/routes/`).

---

## 1. Route Test Coverage Matrix

| Route Module | Endpoints | Test Target | Verification Objectives |
| :--- | :--- | :--- | :--- |
| **`auth.py`** | `POST /auth/register`<br>`POST /auth/login`<br>`POST /auth/refresh` | `TestClient` + DB | 200 on valid credentials; 401 on bad password; duplicate email 400; refresh token rotation. |
| **`device.py`** | `POST /device/activate`<br>`POST /device/deactivate`<br>`GET /devices/` | `TestClient` + DB | Enforce device count per plan; bind fingerprint; reject unauthorized revocation. |
| **`entitlement.py`** | `POST /entitlement/refresh`<br>`GET /entitlement/public-key` | `TestClient` | Return valid RSA signature; public key export matches private key format. |
| **`license.py`** | `POST /license/activate`<br>`POST /license/transfer` | `TestClient` + DB | Device transfer count tracking; monthly limit lockout; status state transitions. |
| **`payment.py`** | `POST /payment/create-order`<br>`POST /payment/verify`<br>`POST /payment/webhook` | `TestClient` + Mock | Order price matching plan; HMAC signature verification; idempotency on duplicate webhook. |
| **`support.py`** | `POST /support/tickets`<br>`GET /support/tickets`<br>`POST /support/crash-report` | `TestClient` + DB | Diagnostics sanitization; error ID linking; ticket serial generation. |
| **`admin.py`** | `GET /admin/metrics`<br>`POST /admin/users/{id}/suspend` | `TestClient` + Key | Role authorization (`require_support`); revenue calculations; audit logging. |
| **`updates.py`** | `GET /updates/check`<br>`GET /updates/releases` | `TestClient` + DB | Channel filtering (`STABLE`/`BETA`); SemVer comparison; signature delivery. |

---

## 2. API Contract Assertions
- All responses must conform to JSON contract: `{"success": bool, ...}` or standard HTTP status codes.
- Every response must include `X-Request-ID` header.
- Unauthorized requests must return 401 with `{"detail": "..."}` without leaking internal stack traces.
