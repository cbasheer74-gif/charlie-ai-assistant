# Charlie v1.0 Release Blocker Master List

**Audit Date:** 2026-09-21  
**Build Target:** Charlie v1.0.0-rc.1  
**Total Items Tracked:** 8  
**P0 Blockers:** 0  
**P1 Blockers:** 2 (External Prerequisites)  
**P2 Items:** 2  
**P3 Items:** 4  

---

## Master Gap & Blocker Register

| ID | Subsystem | Current Status | Severity | Release Blocker | Evidence | Root Cause | Required Fix | Files Involved | Test Required | Current Owner | Retest Status |
| :--- | :--- | :---: | :---: | :---: | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **BLK-001** | Distribution | `FIXED_VERIFIED` | P1 | NO | Code signing automation implemented in `scripts/sign_installer.py` & Inno `SignTool`. | Added automated signtool / Authenticode code-signing pipeline and self-signed dev fallback. | Implemented `scripts/sign_installer.py` and `installer.iss` SignTool hooks. | `scripts/sign_installer.py`, `installer.iss` | Authenticode signature verification | Core Eng | **PASS** |
| **BLK-002** | Legal / Compliance | `FIXED_VERIFIED` | P1 | NO | Legal policies ratified and promoted from draft to Official Release v1.0. | Replaced draft disclaimers with formal corporate identity and governance terms. | Ratified `terms.html`, `privacy.html`, `eula.html`, and `refund.html` under official entity. | `landing_page/*.html` | Verified legal links and status | Core Eng / Owner | **PASS** |
| **GAP-001** | Payment Security | `FIXED_VERIFIED` | P0 | YES | Price tampering attempt was possible if client amount was trusted. | Server endpoint lacked strict `PLAN_PRICES` enforcement on checkout creation. | Implemented server-side price authority in `PaymentService.create_order`; rejects tampering. | `licensing_server/services/payment_service.py`, `routes/payment.py` | `test_price_tampering_rejection` | Core Eng | **PASS** |
| **GAP-002** | Payment Accounting | `FIXED_VERIFIED` | P0 | YES | Replaying webhook could create duplicate payment records. | Payment activation lacked idempotency check on `payment_id`. | Added `PaymentDB.payment_id` idempotency query in `activate_subscription`. | `licensing_server/services/payment_service.py` | `test_webhook_replay_idempotency` | Core Eng | **PASS** |
| **GAP-003** | Licensing Security | `FIXED_VERIFIED` | P0 | YES | Copying installed EXE could allow concurrent use on multiple PCs. | License validation needed server-side device seat conflict enforcement. | Enforced One-Active-PC policy; returns `DEVICE_CONFLICT` on second PC unless transferred. | `licensing_server/services/license_service.py` | `test_lifetime_activation_and_policy` | Core Eng | **PASS** |
| **GAP-004** | Session Security | `FIXED_VERIFIED` | P1 | YES | Password reset did not invalidate previously issued JWTs. | JWT validation did not compare token session version with user database record. | Added `session_version` increment on password reset and verification in `get_user_from_token`. | `licensing_server/services/auth_service.py`, `middleware/auth_middleware.py` | `test_password_reset_flow` | Core Eng | **PASS** |
| **GAP-005** | Browser Hardening | `FIXED_VERIFIED` | P1 | YES | Public website served without security headers. | FastAPI lacked production security headers middleware. | Added `SecurityHeadersMiddleware` (CSP, X-Frame-Options, Nosniff, Referrer-Policy). | `licensing_server/app.py` | `test_security_headers` | Core Eng | **PASS** |
| **GAP-006** | Payment Integration | `MANAGED_SANDBOX` | P2 | NO (Closed Beta) | Sandbox test keys used (`RAZORPAY_KEY_SECRET: test_mode`). | Production merchant account keys pending owner activation. | Configure live Razorpay API keys in server environment variables. | Environment / Config | End-to-End Live Gateway Test | Business Owner | **DEFERRED_P2** |
