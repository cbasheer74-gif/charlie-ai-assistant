# 08 — Authentication & Authorization Test Plan

Target: Security, JWT lifecycle, Session management, and Role enforcement (`licensing_server/services/auth_service.py` & `middleware/auth_middleware.py`).

---

## 1. Authentication Test Cases
- **Password Hashing:** Constant-time bcrypt validation, salt generation, rejection of raw password storage.
- **Access Token:** Expiration after `JWT_ACCESS_EXPIRY_MINUTES`, signature validation using `JWT_SECRET`.
- **Refresh Token:** Rotation and issuance of new access token upon valid refresh presentation.
- **Session Revocation:** Incrementing `session_version` in `UserDB` immediately invalidates previously issued JWTs.
- **Account State Gating:** `account_status == 'BANNED'` must be rejected at middleware layer before route execution.

---

## 2. Role-Based Access Control (RBAC) Matrix
- **`CUSTOMER` / `USER`**: Access to `/me`, `/devices`, `/support/tickets`, `/payment`. Denied `/admin/*`.
- **`SUPPORT`**: Access to read tickets, user diagnostics, view releases. Denied financial payout endpoints.
- **`ADMIN` / `OWNER`**: Full administrative portal access, user bans, entitlement override, release signing.
- **`X-Admin-Key`**: Header-based bypass verification for automated backend microservices.
