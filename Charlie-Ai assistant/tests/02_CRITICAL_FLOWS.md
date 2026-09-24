# 02 — Critical Application Flows

Verified real application flows based on active code inspection.

---

### Flow 1: User Registration & Starter License Provisioning
- **Purpose:** Onboard new user, hash password, create DB records, issue JWTs, and grant STARTER tier entitlement.
- **Entry Point:** `POST /auth/register` (`licensing_server/routes/auth.py`).
- **Dependencies:** `AuthService`, SQLAlchemy `UserDB`, `SubscriptionDB`, `bcrypt`, `jwt`.
- **Success Behavior:** Creates user record with bcrypt-hashed password, creates STARTER subscription (status FREE), returns access + refresh tokens.
- **Failure Cases:** Email already registered (duplicate), password < 8 chars, database connection failure.
- **Risk if Broken:** Complete user onboarding block; revenue and growth halt.
- **Recommended Test Type:** Unit (`AuthService.register`) + API Integration (`TestClient`).

---

### Flow 2: Device Activation & RSA Entitlement Issuance
- **Purpose:** Bind a user license to a physical PC hardware fingerprint and return signed RSA entitlement token.
- **Entry Point:** `POST /device/activate` (`licensing_server/routes/device.py`).
- **Dependencies:** `DeviceService`, `EntitlementSigner`, `DeviceDB`, RSA Private Key.
- **Success Behavior:** Validates subscription status, checks active device count against plan limit, records device fingerprint, returns RSA-signed JWT.
- **Failure Cases:** Device limit reached for plan, invalid/expired auth token, corrupted RSA private key.
- **Risk if Broken:** Paying users locked out from using desktop assistant.
- **Recommended Test Type:** Integration (`device_service` + `entitlement_signer`).

---

### Flow 3: Razorpay Payment Verification & Subscription Activation
- **Purpose:** Verify payment signature from checkout and promote account to paid plan tier.
- **Entry Point:** `POST /payment/verify` (`licensing_server/routes/payment.py`).
- **Dependencies:** `PaymentService`, Razorpay HMAC SHA-256 verifier, `SubscriptionDB`, `LicenseEventDB`.
- **Success Behavior:** Verifies HMAC signature, updates subscription tier (e.g. `PRO`), sets active status, records audit event.
- **Failure Cases:** Invalid signature (tamper attempt), order ID not found, mismatch in expected amount.
- **Risk if Broken:** Customers charged without receiving service (chargebacks, severe reputation damage).
- **Recommended Test Type:** Unit (HMAC validation) + Integration (database state transition).

---

### Flow 4: Desktop Uncaught Crash Interception & Safe Mode Recovery
- **Purpose:** Prevent recurring crash loops from bricking the assistant by catching fatal exceptions and falling back to Safe Mode.
- **Entry Point:** `sys.excepthook` / `threading.excepthook` (`engine/deployment/runtime.py`).
- **Dependencies:** `GlobalExceptionHandler`, `CrashManager`, `DeploymentPathManager`.
- **Success Behavior:** Captures exception, redacts API keys and user paths, writes crash JSON, increments crash counter; if >=2 in 60s, enables `SAFE_MODE`.
- **Failure Cases:** Unhandled exception inside the crash handler itself; disk write failure.
- **Risk if Broken:** App crashes continuously on boot, rendering PC unusable without manual file deletion.
- **Recommended Test Type:** Unit (`CrashManager.record_crash`) + Integration (`test_crash_reporting_diagnostics.py`).

---

### Flow 5: Tool Execution Safety & Audit Chain Verification
- **Purpose:** Intercept desktop automation commands, check against safety policy, and write tamper-evident audit record.
- **Entry Point:** `AuditEngine.record_event()` (`engine/security/audit_engine.py`).
- **Dependencies:** `SecretRedactionEngine`, SHA-256 hash-chain ledger.
- **Success Behavior:** Redacts secrets from arguments, chains previous hash to new record, appends to `audit_chain.jsonl`.
- **Failure Cases:** Tampered ledger (mismatched `prev_hash`), disk write failure.
- **Risk if Broken:** Unauthorized or malicious command execution without forensic traceability.
- **Recommended Test Type:** Unit (`AuditEngine.verify_integrity`).
