# Charlie v1.0 Gap Closure & Resolution Report

**Evaluation Date:** 2026-09-21  
**Build:** Charlie v1.0.0-rc.1  
**Total Identified Gaps:** 6  
**Resolved & Retested:** 5 / 6 (Technical Core 100% Resolved)  
**External Prerequisites:** 2 (Gated for Stable Launch)  

---

## 1. Resolved Technical Gaps

### GAP-001: Price Tampering Rejection
- **Original Status:** `FAIL / PARTIAL`
- **Root Cause:** Client-submitted price in checkout payload could diverge from configured catalog.
- **Fix Applied:** `PaymentService.create_order` was modified to strictly look up `PLAN_PRICES[plan]` server-side. Any client mismatch triggers `TAMPER_DETECTED` and immediately aborts order creation.
- **Automated Evidence:** `test_price_tampering_rejection` in `tests/test_public_commercial_platform.py` passes with zero errors.
- **Final Status:** **PASS**

### GAP-002: Webhook Idempotency & Duplicate Charge Prevention
- **Original Status:** `FAIL / PARTIAL`
- **Root Cause:** Replaying a webhook event could re-execute `activate_subscription` and create multiple duplicate `PaymentDB` records.
- **Fix Applied:** Implemented unique `payment_id` lookup in `PaymentDB` before processing activation. Existing verified payment returns idempotent success.
- **Automated Evidence:** `test_webhook_replay_idempotency` passes with zero duplicate records.
- **Final Status:** **PASS**

### GAP-003: Multi-PC Concurrent Piracy Enforcement
- **Original Status:** `FAIL / PARTIAL`
- **Root Cause:** Copying installation directory to a secondary PC required strict seat enforcement.
- **Fix Applied:** `LicenseService.activate_device` validates `active_device_id`. If active on a different device, it blocks activation with `DEVICE_CONFLICT` and requires an authenticated transfer.
- **Automated Evidence:** `test_lifetime_activation_and_policy` verifies second PC activation is blocked until transfer.
- **Final Status:** **PASS**

### GAP-004: JWT Revocation on Password Reset
- **Original Status:** `FAIL / PARTIAL`
- **Root Cause:** Resetting a password updated the hash but left active JWT tokens valid until natural expiration.
- **Fix Applied:** `AuthService.reset_password` increments `UserDB.session_version`. Token validation checks `session_version` and revokes old tokens immediately.
- **Automated Evidence:** `test_password_reset_flow` confirms old refresh tokens are rejected.
- **Final Status:** **PASS**

### GAP-005: Security Headers & Production Hardening
- **Original Status:** `PARTIAL`
- **Root Cause:** Missing Content Security Policy and frame denial headers.
- **Fix Applied:** `SecurityHeadersMiddleware` added to `licensing_server/app.py` returning `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Content-Security-Policy`.
- **Automated Evidence:** `test_security_headers` passes on all HTTP endpoints.
- **Final Status:** **PASS**

---

## 2. External Gaps Gated on Business Owner

| Gap ID | Description | Required Action | Status |
| :--- | :--- | :--- | :---: |
| **BLK-001** | Production EV Code Signing Certificate | Owner acquires EV certificate and signs `Charlie-Setup.exe`. | **EXTERNAL_BLOCKED** |
| **BLK-002** | Legal Counsel Document Ratification | Legal counsel reviews `terms.html`, `privacy.html`, `refund.html`, `eula.html`. | **EXTERNAL_BLOCKED** |
