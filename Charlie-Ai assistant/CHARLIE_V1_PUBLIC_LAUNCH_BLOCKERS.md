# CHARLIE v1.0 Public Launch Blockers Registry

**Evaluation Date:** 2026-09-21  
**Build Target:** CHARLIE v1.0.0-rc.1  
**Authority:** Launch Readiness Audit & Automated Testing  

---

## 1. Blocker Summary

| Severity | Count | Status | Notes |
| :--- | :--- | :--- | :--- |
| **P0 (Critical Blocker)** | **0** | **RESOLVED** | Zero data loss, zero payment tampering, zero credential leakage. |
| **P1 (Launch Risk / Prerequisite)** | **2** | **ACTION REQUIRED** | Code Signing Certificate & Formal Legal Counsel Ratification. |
| **P2 (Controlled Risk)** | **1** | **MANAGED** | Live payment gateway keys (currently in Test Mode sandbox). |
| **P3 (Minor / Informational)** | **0** | **CLEARED** | Copy, routing, and UI responsiveness verified. |

---

## 2. Active Launch Prerequisites (P1)

### BLK-001: Production EV Code-Signing Certificate
- **Severity:** P1 (Release Risk)
- **Component:** Installer & Auto-Updater Distribution
- **Current State:** `CHARLIE-Setup.exe` (158 MB) is currently compiled without an Extended Validation (EV) code-signing certificate (`CODE_SIGNING: NOT_CONFIGURED`).
- **Impact:** Windows Defender SmartScreen displays an informational prompt on first run until certificate reputation is built.
- **Required Owner Action:** Business owner must acquire and configure an EV code-signing certificate in the build pipeline.
- **Release Gating:** Blocks `READY_FOR_STABLE_PUBLIC_LAUNCH`. Does NOT block `READY_FOR_CONTROLLED_PUBLIC_LAUNCH` (Beta/Test cohort).

### BLK-002: Formal Legal Counsel Ratification
- **Severity:** P1 (Compliance Risk)
- **Component:** Legal Compliance (`terms.html`, `privacy.html`, `refund.html`, `eula.html`)
- **Current State:** Pages deployed with explicit status `DRAFT_REQUIRES_REVIEW`.
- **Impact:** Commercial terms must be legally binding in target jurisdictions (India/International) prior to unrestricted public advertising.
- **Required Owner Action:** Legal counsel must review and sign off on governing jurisdiction and company registration details.
- **Release Gating:** Blocks unrestricted marketing; ready for closed beta / controlled public pilot.

---

## 3. Technical Blockers (Resolved)

| ID | Issue | Root Cause | Fix Applied | Retest Status |
| :--- | :--- | :--- | :--- | :--- |
| **FIX-001** | Price Tampering Vulnerability | Client could submit modified price JSON | Server computes price strictly from `PLAN_PRICES`; rejects mismatches with `TAMPER_DETECTED` event. | **PASS** |
| **FIX-002** | Webhook Replay Vulnerability | Replayed webhooks could duplicate revenue | Idempotency verification via `PaymentDB.payment_id` prevents duplicate entitlement. | **PASS** |
| **FIX-003** | Concurrent Multi-PC Piracy | Copying installer could enable concurrent use | Server enforces 1 Active PC; second PC receives `DEVICE_CONFLICT` requiring authenticated transfer. | **PASS** |
| **FIX-004** | Session Stale Invalidation | Password reset didn't revoke existing JWTs | `session_version` incremented on reset; old tokens invalidated immediately. | **PASS** |
