# 03 — Test Matrix

Planning matrix mapping verified subsystems to required test coverage and priorities.

| Area | Feature / Behavior | Unit | Integration | E2E / Functional | Priority | Existing Coverage |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Authentication** | Password Bcrypt Hashing | [x] | [ ] | [ ] | **P0** | Present (`test_commercial_control_system.py`) |
| **Authentication** | JWT Expiration & Validation | [x] | [x] | [ ] | **P0** | Present |
| **Authentication** | Session Invalidation (`session_version`) | [x] | [x] | [ ] | **P1** | Present |
| **Licensing** | Plan Tier Feature Gating | [x] | [ ] | [ ] | **P0** | Present (`feature_gate.py`) |
| **Licensing** | RSA Entitlement Signing | [x] | [x] | [ ] | **P0** | Present |
| **Licensing** | Device Limit Enforcement | [ ] | [x] | [ ] | **P1** | Present |
| **Licensing** | Monthly Transfer Quota | [ ] | [x] | [ ] | **P1** | Present |
| **Billing** | Razorpay Signature Verification | [x] | [ ] | [ ] | **P0** | Present |
| **Billing** | Webhook Idempotency & Handling | [ ] | [x] | [ ] | **P0** | Partial |
| **Billing** | Credit Wallet Deductions & Reset | [x] | [x] | [ ] | **P1** | Present (`test_commercial_monetization.py`) |
| **Observability** | Request ID Header Propagation | [x] | [x] | [ ] | **P1** | Present (`test_observability_middleware.py`) |
| **Observability** | Structured JSON Logging Format | [x] | [x] | [ ] | **P1** | Present |
| **Observability** | Deep `/health` (DB + RSA + Disk) | [x] | [x] | [ ] | **P1** | Present |
| **Observability** | SQL Slow-Query Event Interception | [x] | [x] | [ ] | **P2** | Partial |
| **Observability** | Rate Limit 429 Security Logging | [x] | [x] | [ ] | **P2** | Partial |
| **Security** | Tamper-Evident SHA-256 Audit Chain | [x] | [ ] | [ ] | **P0** | Present (`test_phase9_security.py`) |
| **Security** | Command Blacklist & Sanitization | [x] | [ ] | [ ] | **P0** | Present |
| **Security** | Secret Scrubbing in Crash Bundles | [x] | [ ] | [ ] | **P0** | Present (`test_crash_reporting_diagnostics.py`) |
| **Runtime** | Uncaught Exception Interception | [x] | [x] | [ ] | **P0** | Present |
| **Runtime** | Safe Mode Crash-Loop Protection | [x] | [x] | [ ] | **P0** | Present |
| **AI / LLM** | Model Fallback Ladder (Gemini Live/REST) | [x] | [ ] | [ ] | **P2** | Partial |
| **AI / LLM** | Ollama Local Process Detection | [x] | [ ] | [ ] | **P2** | Partial |
