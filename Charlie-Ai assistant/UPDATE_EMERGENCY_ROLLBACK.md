# CHARLIE Emergency Release Rollback Runbook

**Standard Operating Procedure for Immediate Halting, Revocation, and Recovery of Defective Updates.**

---

## 1. When to Trigger Emergency Rollback

Trigger immediately if any of the following occur:
- Elevated startup crash rate (> 1.5% of cohort).
- Critical regression affecting payment, licensing, or local user data.
- Security vulnerability reported in the newly distributed binary.

---

## 2. Emergency Operational Sequence

### Step 1: Immediate Rollout Pause (< 2 Minutes)
Halt all new client updates immediately via the Admin API:
```http
POST /updates/releases/{version}/pause
X-Admin-Key: <ADMIN_KEY>
```
*Effect:* Any client running an update check will be told "CHARLIE is up to date." No further downloads will initiate.

---

### Step 2: Formal Release Revocation (< 5 Minutes)
Mark release status as `REVOKED`:
```http
POST /updates/releases/{version}/revoke
X-Admin-Key: <OWNER_KEY>

{
  "reason": "Critical startup crash in video rendering module"
}
```
*Effect:* Any client that downloaded the package but has not installed it will reject the installation.

---

### Step 3: Automated Client-Side Rollback
1. Affected client installations will trigger `PostUpdateHealthChecker`.
2. When launch validation fails or crashes repeat (>= 3 attempts), `RollbackManager` will:
   - Revert binary to previous version.
   - Restore database and configuration from `pre_update_{version}_{timestamp}.zip`.
   - Present non-technical message to customer:
     > *"The latest update could not start correctly. CHARLIE restored the previous working version."*

---

### Step 4: Root Cause Investigation & Patching
1. Collect sanitized diagnostic bundles from affected clients (`GET /admin/api/support/tickets`).
2. Verify that API keys and personal data are scrubbed via `SecretRedactor`.
3. Reproduce issue in development sandbox.
4. Prepare fixed patch release (e.g. `v1.0.2`) following standard `RELEASE_RUNBOOK.md`.
