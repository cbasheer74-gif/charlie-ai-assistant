# 04 — Risk-Based Test Plan

Project-specific architectural and operational risks with code references and test verification plans.

---

### Risk 1: Cryptographic License Forgery / Entitlement Bypass
- **Evidence:** `licensing_server/services/entitlement_signer.py` signs JWT payload using RSA private key; `engine/commercial/entitlement_verifier.py` verifies using public key.
- **Affected Files:** `licensing_server/services/entitlement_signer.py`, `licensing_server/keys/`, `engine/commercial/`.
- **Failure Scenario:** If the client fails to verify RSA signature or accepts `alg: none` / unverified tokens, users can self-sign `LIFETIME` plan entitlements.
- **Impact:** Total loss of software revenue; unauthorized feature usage.
- **Required Test:** Negative test passing forged signature, modified claims, and unsigned JWTs to `entitlement_verifier`. Assert rejection.
- **Priority:** **P0**

---

### Risk 2: Payment Webhook Dropping Activation Silently
- **Evidence:** `licensing_server/routes/payment.py:100` checks `notes.get("user_id")` and `notes.get("plan")`. If missing, execution skips `activate_subscription` and returns `{"success": True}`.
- **Affected Files:** `licensing_server/routes/payment.py`, `licensing_server/services/payment_service.py`.
- **Failure Scenario:** Razorpay charges customer, but metadata notes are truncated or omitted. Account activation never occurs, with zero error logs.
- **Impact:** Customer charged without service, immediate chargebacks, reputational damage.
- **Required Test:** Webhook payload tests with missing `user_id` asserting warning/error status code and event capture in `RazorpayEventDB`.
- **Priority:** **P0**

---

### Risk 3: Desktop Startup Crash-Loop Deadlock
- **Evidence:** `engine/deployment/runtime.py:288` monitors crashes within 60s window.
- **Affected Files:** `engine/deployment/runtime.py`, `engine/deployment/crash_reporter.py`.
- **Failure Scenario:** A broken update causes the process to crash immediately on launch. If the crash detector fails, Windows repeatedly relaunches and crashes in an infinite loop.
- **Impact:** Unusable user system, high CPU load, unrecoverable state.
- **Required Test:** Simulate 3 consecutive crashes; assert `AppHealthState.SAFE_MODE` is activated and minimal UI boots with error dialog.
- **Priority:** **P0**

---

### Risk 4: Private Credential Leak in Diagnostic Support Uploads
- **Evidence:** Users report bugs with diagnostic logs uploaded to `licensing_server/routes/support.py`.
- **Affected Files:** `engine/deployment/diagnostic_collector.py`, `licensing_server/services/support_service.py`.
- **Failure Scenario:** Log bundles contain raw Gemini API keys, OpenAI keys, Windows usernames, or database connection strings.
- **Impact:** Serious privacy and security violation; credential compromise.
- **Required Test:** Golden test feeding strings with API keys, JWTs, and `C:\Users\username\` through `SecretRedactor`. Assert 100% redacted output.
- **Priority:** **P0**

---

### Risk 5: SQLite Database Concurrency Locking
- **Evidence:** `licensing_server/database.py` defaults to local SQLite file when environment variables are omitted.
- **Affected Files:** `licensing_server/database.py`.
- **Failure Scenario:** Multiple concurrent API requests (e.g. login + webhook + health) lock the SQLite database (`OperationalError: database is locked`).
- **Impact:** 500 internal server errors, dropped payments, failed logins.
- **Required Test:** Concurrent connection stress test verifying timeout parameters and connection retry logic.
- **Priority:** **P1**
