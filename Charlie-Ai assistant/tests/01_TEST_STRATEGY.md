# 01 — Test Strategy

**Project:** Charlie AI Assistant (Desktop Client + FastAPI Licensing Backend)  
**Ecosystem:** Python 3.10+ / PyQt5 / FastAPI / SQLAlchemy / Pytest & Unittest  
**Test Directory:** `Charlie-Ai assistant/tests/`

---

## 1. Project Test Objective
Ensure deterministic verification of desktop autonomy, crash resilience, cryptographic licensing enforcement, and financial billing workflows without regression or unhandled exceptions in production binaries.

---

## 2. Test Framework & Directory Convention
- **Framework:** Python standard library `unittest` (with `pytest` runner compatibility) and Starlette `TestClient` for FastAPI endpoint isolation.
- **Convention:** `Charlie-Ai assistant/tests/test_*.py`.
- **Naming Pattern:** `test_<subsystem>_<feature>.py`.

---

## 3. Unit Testing Strategy
- **Scope:** Isolated pure logic, algorithms, state machines, parsers, and cryptographic validators.
- **Target Subsystems:**
  - `engine/security/audit_engine.py`: SHA-256 hash chaining, genesis root integrity, tamper detection.
  - `engine/security/command_safety.py`: Blacklisted command patterns, path traversal prevention.
  - `licensing_server/services/entitlement_signer.py`: RSA-4096 signing, payload canonicalization, signature validation.
  - `engine/deployment/diagnostic_collector.py`: Sensitive token & username path redaction regexes.
  - `engine/commercial/feature_gate.py`: Plan tier entitlement matrix (`STARTER` -> `PRO` -> `LIFETIME`).

---

## 4. Integration Testing Strategy
- **Scope:** Multi-component interactions across service boundaries.
- **Target Flows:**
  - **Auth -> Database -> Token Session:** Registration, bcrypt hashing, JWT issuance, session invalidation via `session_version`.
  - **Checkout -> Webhook -> Activation:** Razorpay order initialization, signature verification, `SubscriptionDB` activation, `LicenseEventDB` ledger write.
  - **Desktop Crash -> Reporter -> Support Ingestion:** `GlobalExceptionHandler` interception, diagnostic scrubbing, local bundle serialization, support ticket attachment.
  - **Middleware Pipeline:** `RequestIdMiddleware` -> `StructuredLoggingMiddleware` -> Endpoint execution -> Response headers.

---

## 5. What Should NOT Be Tested
- **Third-Party Live Endpoints:** Do NOT execute live network calls against Razorpay production APIs or production Gemini quota during standard CI/test runs.
- **Physical Audio Hardware:** Do NOT assert physical microphone or speaker device presence in automated suites; test through virtual device abstraction (`audio_devices.py`).
- **OS Window Compositing:** Do NOT test OS desktop window transparency or GPU rendering passes in headless CI.

---

## 6. Test Priorities
- **P0:** Licensing bypass prevention, cryptographic signature forgery, payment activation failure, crash-loop deadlocks.
- **P1:** Authentication, token expiration, credit wallet balance calculations, device binding & transfer limits.
- **P2:** Voice pipeline state transitions, model fallback ladder, diagnostic sanitization.
- **P3:** UI theme stylesheet loading, avatar idle animation frame rates.

---

## 7. Test Execution Philosophy
Tests must run self-contained against in-memory or ephemeral SQLite fixtures (`sqlite:///:memory:`) without external cloud dependencies, leaving zero persistent artifacts or disk pollution after completion.
