# Charlie v1.0 Gap Closure Plan

**Audit Target:** Charlie v1.0.0-rc1  
**Scope:** Gap Resolution & Stabilization across Phases 1–15  
**Guiding Principle:** DO NOT add new features. Close architectural gaps, verify edge cases, and ensure deterministic reliability before launch.

---

## 1. Prioritization Hierarchy

All gaps are categorized and ordered by strict architectural dependency:

1. **Tier 1 (P0):** Security vulnerabilities, credential exposure, data loss, unrecoverable crashes.
2. **Tier 2 (P1):** Core functional breakdowns, broken task resume, unverified rollbacks.
3. **Tier 3 (Core Architecture):** Phases 1–3 foundational integrity (Memory, Computer Control, Autonomy).
4. **Tier 4 (Security & Recovery):** Phase 9 policy enforcement, audit integrity, disaster recovery.
5. **Tier 5 (QA & Certification):** Phase 13 empirical test evidence, Golden Master scenarios.
6. **Tier 6 (Deployment & Runtime):** Phase 14 installer, single instance, onboarding, update rollback.
7. **Tier 7 (Launch Operations):** Phase 15 UAT, triage, runbooks, Go/No-Go decision gates.
8. **Tier 8 (P2 Gaps):** Non-blocking functional limitations.
9. **Tier 9 (POST_V1):** Ecosystem expansions deferred to v1.1.

---

## 2. Master Gap Closure Matrix

| Gap ID | Subsystem | Description | Severity | Classification | Target Resolution | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **GAP-01** | Phase 9 Security | Secret leakage in exception stack traces | P0 | `V1_BLOCKER` | Automated regex redaction in `CrashManager` & `vault.py` | **RESOLVED & VERIFIED** |
| **GAP-02** | Phase 14 Runtime | Startup crash loop leading to infinite restart | P1 | `V1_BLOCKER` | Automatic transition to `SAFE_MODE` on >=2 crashes in 60s | **RESOLVED & VERIFIED** |
| **GAP-03** | Phase 14 Packaging | Single instance mutex collision detection in test process | P1 | `V1_BLOCKER` | PID verification logic fixed in `SingleInstanceManager` | **RESOLVED & VERIFIED** |
| **GAP-04** | Phase 15 Launch | Missing `VOICE` attribute in `UATPersona` enum | P1 | `V1_BLOCKER` | Add `VOICE = "VOICE"` to `UATPersona` in `engine/launch/models.py` | **RESOLVED & VERIFIED** |
| **GAP-05** | Phase 15 Pilot | String vs Enum type mismatch in `register_device` | P1 | `V1_BLOCKER` | Auto-cast string cohort to `PilotStage` in `uat_pilot.py` | **RESOLVED & VERIFIED** |
| **GAP-06** | Phase 6 Office | Native Google Workspace OAuth2 API integration | P2 | `POST_V1` | Defer headless API client; use browser automation for v1.0 | **DEFERRED TO v1.1** |
| **GAP-07** | Phase 10 Mobile | Standalone iOS / Android mobile companion app binaries | P2 | `POST_V1` | Windows host gateway & sync engine verified; client app in v1.1 | **DEFERRED TO v1.1** |
| **GAP-08** | Phase 7 Voice | Unclosed SQLite database warning in voice tests | P3 | `V1_OPTIONAL` | Explicit database connection closing in voice test teardown | **RESOLVED / ACCEPTED** |
| **GAP-09** | Phase 7 Voice | Wake word degradation in high background noise | P2 | `V1_OPTIONAL` | Document Push-to-Talk workaround in `KnownIssuesManager` | **CATALOGED AS KI_01** |
| **GAP-10** | Phase 11 AI | Cold-start latency on 8GB RAM systems | P2 | `V1_OPTIONAL` | Document in `KnownIssuesManager` (KI_02) with cloud fallback | **CATALOGED AS KI_02** |

---

## 3. Detailed Gap Closure Actions & Evidence

### GAP-01: Secret Leakage Redaction (Tier 1 - P0)

- **Problem:** Unhandled exceptions might expose raw API keys or connection strings in logs.
- **Action Taken:** `CrashManager.redact_secrets()` and `CredentialVault.scrub()` implemented with strict regex matching for `sk-...`, `Bearer ...`, and passwords.
- **Verification:** `tests/test_phase14_deployment.py::test_11_crash_manager_secret_redaction` passed.

### GAP-02: Crash Loop Safe Mode (Tier 2 - P1)

- **Problem:** If a bad extension causes a startup crash, Charlie could enter an infinite restart loop.
- **Action Taken:** `CrashManager` tracks crash timestamps. If >=2 crashes occur within 60 seconds, `AppHealthState.SAFE_MODE` is activated, disabling optional extensions and computer control.
- **Verification:** `tests/test_phase14_deployment.py::test_12_crash_loop_safe_mode` passed.

### GAP-03: Single Instance Lock Acquisition (Tier 2 - P1)

- **Problem:** In `SingleInstanceManager._is_pid_running`, checking `pid == os.getpid()` returned `False`, causing lock collisions within test processes.
- **Action Taken:** Fixed `_is_pid_running` to return `True` for active PIDs.
- **Verification:** `tests/test_phase14_deployment.py::test_07_single_instance_lock` passed.

### GAP-04 & GAP-05: Phase 15 Enum and Cohort Type Validation (Tier 2 - P1)

- **Problem:** Missing `VOICE` persona in `UATPersona` and unhandled string cohort in `register_device`.
- **Action Taken:** Updated `models.py` with `VOICE = "VOICE"` and added type coercion in `uat_pilot.py`.
- **Verification:** `tests/test_phase15_launch.py` (all 20 tests) passed.

---

## 4. Scope Classification for Deferred Items (POST_V1)

1. **Native Google Workspace OAuth2 API (`POST_V1`):**
   - Headless direct API integration (Google Calendar, Gmail, Google Drive REST APIs) is planned for v1.1.
   - For v1.0, Playwright DOM automation (`actions/browser_control.py`) and local spreadsheet automation (`actions/excel_worker.py`) provide comprehensive functionality without complex Google Cloud OAuth app verification.
2. **Native Mobile Companion App (`POST_V1`):**
   - The desktop host gateway (`engine/devices/gateway.py`), encrypted pairing, and selective memory sync are fully implemented and verified.
   - The standalone Flutter Android/iOS companion application binary is scheduled for the v1.1 ecosystem roadmap.

---

## 5. Next Steps for v1.0 Launch Candidate

1. **Repository Freeze:** Enforce `FreezeState.CODE_FREEZE` via `ReleaseFreezeManager`.
2. **Build Stamping:** Execute `BuildManager.generate_build_metadata()` for `v1.0.0-rc1`.
3. **Controlled Pilot:** Deploy `Charlie-Setup.exe` to Dogfood and Beta cohorts.
4. **Final Go-Live:** Execute staged rollout (5% → 20% → 50% → 100% Stable).
