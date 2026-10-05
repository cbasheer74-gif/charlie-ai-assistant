# Production Pre-Release Checklist

This checklist must be executed and signed off prior to publishing any production or staging build of CHARLIE.

---

## 1. Code & Build Integrity Validation

- [ ] **Working Tree**: Repository working tree is clean (`git status` shows no uncommitted changes).
- [ ] **Automated Test Suite**: Full test suite passes with 0 failures:

  ```powershell
  pytest tests/ -v
  ```

- [ ] **Secret Scanning**: Pre-build secret scanner in `build_production.py` passes without errors.
- [ ] **RSA Entitlement Key**: `licensing_server/keys/entitlement_verify.pub` is present and successfully embedded into `engine/commercial/entitlement_verifier.py`.
- [ ] **Integrity Manifest**: `engine/commercial/integrity_manifest.json` is freshly computed and matches built modules.
- [ ] **Build Stamping**: Version number and build number in `build_metadata.json` match `installer.iss` and `VERSION`.
- [ ] **Executable Verification**: `dist/CHARLIE/CHARLIE.exe` starts without missing DLL errors or Python runtime exceptions.
- [ ] **Installer Generation**: `dist/CHARLIE-Setup-<version>.exe` compiles successfully via Inno Setup.

---

## 2. Environment & Secrets Verification

- [ ] **Production Flag**: `CHARLIE_ENV=production` is set in production deployment target.
- [ ] **Admin Secret**: `CHARLIE_ADMIN_KEY` is set to a secure, random string (NOT `charlie_admin_secret_key_2026`).
- [ ] **JWT Secret**: `CHARLIE_JWT_SECRET` is set to a secure, high-entropy 256-bit key.
- [ ] **Razorpay Keys**: Live API keys (`RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`) are configured and verified.
- [ ] **Email Delivery**: SMTP credentials (`CHARLIE_SMTP_HOST`, `USER`, `PASSWORD`) are verified with a test email.
- [ ] **No Leaked Secrets**: `dist/` and release output directories contain zero raw credentials or private keys.

---

## 3. Database & Migration Readiness

- [ ] **Database Backup**: Full snapshot of production `charlie_licensing.db` or PostgreSQL cluster taken prior to release.
- [ ] **Schema Compatibility**: Any new columns added to `licensing_server/database.py` are nullable or have defaults to avoid breaking older running instances.
- [ ] **Idempotent Migrations**: `init_db()` runs cleanly without raising duplicate column exceptions.

---

## 4. API & Cross-Tier Compatibility

- [ ] **Backward Compatibility**: Newer licensing server supports older client telemetry payloads and activation requests.
- [ ] **Admin Control Panel**: Static web assets in `admin_panel/` load cleanly without 404s or console errors on both Light and Dark themes.
- [ ] **Offline Grace Logic**: Client verifier correctly allows 14-day (monthly) and 90-day (lifetime) offline execution without network errors.

---

## 5. Deployment & Release Execution

- [ ] **Channel Allocation**: Release is initially registered to `BETA` channel:

  ```http
  POST /updates/releases
  {"channel": "BETA", ...}
  ```

- [ ] **Checksum Match**: SHA-256 registered in server manifest exactly matches `CertUtil -hashfile dist\CHARLIE-Setup-<version>.exe SHA256`.
- [ ] **Staged Rollout Plan**:
  - [ ] 5% Canary Cohort (monitor crash logs for 12 hours)
  - [ ] 25% Cohort
  - [ ] 50% Cohort
  - [ ] 100% General Availability

---

## 6. Post-Deployment Verification (Smoke Tests)

- [ ] **Server Health Endpoint**: `GET /health` returns HTTP 200 `{"status": "healthy"}`.
- [ ] **Admin Authentication**: Login to `http://<server>:8400/admin-panel/` with `X-Admin-Key` succeeds.
- [ ] **Overview KPIs**: Dashboard loads real user counts, hardware nodes, and MRR.
- [ ] **Client Activation Test**: A test client successfully binds a hardware fingerprint and verifies entitlement token.
- [ ] **Crash Telemetry Pipeline**: Verify that test diagnostic events sent to `/api/support/tickets` appear with all secrets redacted.

---

## 7. Rollback Readiness Sign-Off

- [ ] **Rollback Runbook Available**: Operations team has access to `deployment/rollback.md` and `UPDATE_EMERGENCY_ROLLBACK.md`.
- [ ] **Pause/Revoke Endpoints Verified**: `POST /updates/releases/{version}/pause` is accessible and functional.
- [ ] **Previous Version Preserved**: The previous official installer binary (e.g. `v1.2.2`) is archived and immediately accessible for emergency reversion.
