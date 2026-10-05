# CHARLIE Public Commercial Platform Security Review

**Review Date:** 2026-09-21  
**Scope:** Public Website, Authentication API, Checkout Engine, Licensing Gateway, Release Distribution  
**Security Status:** PASS &bull; ZERO CRITICAL VULNERABILITIES  

---

## 1. Executive Summary

This security audit assesses the attack surface of the CHARLIE public commercial entry point. The platform enforces server-side pricing authority, cryptographic licensing, zero client financial credential storage, and strict browser hardening.

---

## 2. Threat Vector Evaluation

| Threat Vector | Evaluation & Mitigations | Status |
| :--- | :--- | :--- |
| **Price Tampering** | Orders are created exclusively via `POST /payment/create-order` where the server computes `PLAN_PRICES[plan]`. If a client passes a tampered amount (e.g. ADVANCED for ₹99), the server immediately rejects the request, blocks order creation, and logs a `TAMPER_DETECTED` license event. | **PASS** |
| **Client Payment Spoofing** | Redirecting to `/payment-success` or claiming client success does NOT grant entitlements. Subscriptions are activated only upon server-side verification of Razorpay HMAC signatures (`POST /payment/verify`) or verified webhooks. | **PASS** |
| **Webhook Replay Attacks** | `PaymentService.activate_subscription` checks `PaymentDB` for existing verified `payment_id`. Replayed webhooks return idempotent success without duplicating revenue, subscription cycles, or audit logs. | **PASS** |
| **Credential Storage** | Plaintext passwords are never stored. Passwords are hashed server-side using bcrypt with unique salts. Debit/credit card numbers, CVVs, and UPI PINs are processed directly by Razorpay and never touch CHARLIE servers. | **PASS** |
| **Account Enumeration** | `POST /auth/forgot-password` returns a generic success message regardless of whether the target email exists in the database. | **PASS** |
| **Session Invalidation** | Password resets increment `UserDB.session_version`, instantaneously invalidating all previously issued JWT tokens and refresh tokens. | **PASS** |
| **Secret Exposure** | Client JavaScript (`landing_page/script.js`) contains zero API keys, webhook secrets, database credentials, or RSA private keys. Only the public key ID (`RAZORPAY_KEY_ID`) is returned for gateway rendering. | **PASS** |
| **Software Distribution Integrity** | The public distribution is strictly `CHARLIE-Setup.exe` (158 MB compiled installer with SHA-256 `dc660decad27081289f44423b19940e09f4c35a353a457703b090f21d7ef2aa2`). No source ZIP or repository archives are exposed. | **PASS** |
| **Browser Security Headers** | The FastAPI backend enforces `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-XSS-Protection: 1; mode=block`, and Content Security Policy (`CSP`). | **PASS** |

---

## 3. Cryptographic Verification Matrix

- **Licensing Tokens:** Signed server-side using 2048-bit RSA private keys; verified on desktop via public key.
- **Payment Verification:** HMAC-SHA256 verification using server-side `RAZORPAY_KEY_SECRET`.
- **Webhook Authenticity:** HMAC-SHA256 signature verification on raw request body using `RAZORPAY_WEBHOOK_SECRET`.
- **Device Identity:** Non-reversible SHA-256 salted hash of hardware attributes; raw MAC and serials are never collected.
