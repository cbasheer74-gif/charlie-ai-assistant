# 13 — Security Test Plan

Target: Cryptographic controls, tool sandbox, command safety, secret redaction, and rate limiting.

---

## 1. Test Targets & Vulnerability Verifications

### 1. Cryptographic Audit Ledger (`engine/security/audit_engine.py`)
- **Genesis Hash:** Initial record binds to `GENESIS_ROOT_HASH`.
- **Hash Chaining:** Every subsequent record calculates SHA-256 over `prev_hash | payload`.
- **Tamper Detection:** Altering any line, timestamp, or verdict triggers `verify_integrity()` failure.

### 2. Desktop Command Blacklist (`engine/security/command_safety.py`)
- **Destructive Commands:** Block execution of `format`, `rmdir /s /q c:\`, `del /f /s /q c:\windows`, `diskpart`.
- **Path Traversal:** Block shell execution targeting `../../` escapes outside permitted directories.

### 3. Diagnostic Secret Scrubbing (`engine/deployment/diagnostic_collector.py`)
- **API Keys:** Scrub Google Gemini (`AIza...`), OpenAI/Anthropic (`sk-...`), and generic bearer tokens.
- **Personal Paths:** Anonymize `C:\Users\<username>\` to `C:\Users\[USER]\`.
- **Database Strings:** Scrub `postgres://user:password@host` credentials.

### 4. Rate Limiting Protection (`licensing_server/middleware/rate_limiter.py`)
- **Threshold Gating:** Assert HTTP 429 when requests exceed `LOGIN_RATE_LIMIT` or `ACTIVATION_RATE_LIMIT`.
- **Security Event Emission:** Verify structured JSON security log is emitted upon limit breach.
