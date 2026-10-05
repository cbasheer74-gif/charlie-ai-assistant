# CHARLIE Crash Reporting, Remote Diagnostics & Support System Audit

**Audit Date:** 2026-09-21  
**Target:** Production Windows Desktop AI Assistant (CHARLIE)

---

## 1. Executive Summary

Audit of existing components across desktop client, runtime management, security engine, and commercial licensing backend. Evaluated for crash interception, privacy preservation, diagnostic collection, incident grouping, remote diagnostics, and support integration.

---

## 2. Component Capability Matrix

| Component | Existing File | Current Capability | Status | Missing Requirement | Recommended Change |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CrashManager** | `engine/deployment/runtime.py` | Basic file output in `diagnostics/`, 60s crash loop tracking (`>=2` crashes triggers safe mode flag). | **PARTIAL** | No crash ID (`CHARLIE-CRASH-XXXXXX`), no stack signature, no error level classification (`INFO`..`FATAL`), no path anonymization. | Upgrade with crash IDs, structured levels, stable stack signature hashing, path redaction. |
| **ErrorHandler / Global Hook** | `engine/error_recovery.py` | 2-strike tool policy, error signature extraction from messages. | **PARTIAL** | No global exception hook (`sys.excepthook`, `threading.excepthook`, async tasks, startup failures). | Implement `GlobalExceptionHandler` with multi-thread and async task failure interception. |
| **Logging System** | `engine/deployment/paths.py` | Direct log file pointer `logs/charlie.log`. | **PARTIAL** | Log rotation missing, size limits missing, structured fields missing. | Add structured log handler with max size, rotation, and privacy filters. |
| **StructuredLogger** | *None* | Plain text log writes in various modules. | **MISSING** | JSON/structured event logs with `task_id`, `crash_id`, `component`. | Implement structured logger format helper. |
| **AuditEngine** | `engine/security/audit_engine.py` | Cryptographic SHA-256 hash-chained ledger for security and tool actions. | **PASS** | Incident linking to audit events. | Connect crash and diagnostic export events to `AuditEngine`. |
| **SupportService** | `licensing_server/services/support_service.py` | Ticket creation, secret redaction (Gemini, OpenAI, Bearer, JWT), staff notes. | **PARTIAL** | No incident grouping, no remote diagnostic request/consent workflow, no version correlation. | Add `IncidentGroupingEngine`, consent tracking, and diagnostic upload handling. |
| **Admin Dashboard** | `licensing_server/services/admin_service.py` & web | User management, license resets, release management, audit view. | **PARTIAL** | No Support Center view, no Incident grouping list (`SEV0`..`SEV3`), no crash analytics. | Add Support Center and Incident Management routes and views. |
| **Customer Portal** | `engine/commercial/ui_components.py` & web | Plan view, license status, device transfer. | **PARTIAL** | No "Help & Support" tab, no ticket creation UI, no crash recovery prompt. | Implement `SupportCenterWidget` and `CrashRecoveryDialog`. |
| **ReleaseManager** | `licensing_server/services/update_service.py` | Signed releases, channels, SHA-256 verification, rollouts. | **PASS** | Correlation of crash spikes to specific versions/releases. | Link crash incident analytics to `ReleaseManager`. |
| **UpdateManager** | `engine/deployment/update_manager.py` | Signed update detection, staging, validation, rollback. | **PASS** | Health verification integration after update. | Feed post-update crash signals into update health checker. |
| **DeviceManager** | `engine/devices/` & licensing | Device fingerprinting, one-active-PC, transfer events. | **PASS** | Hardware fingerprint exposed in logs. | Hash/normalize device ID in diagnostic bundles (`device_id_hash`). |
| **Licensing System** | `licensing_server/` & `engine/commercial/` | Entitlement signing, feature gating, plan verification. | **PASS** | Diagnostic state extraction. | Add safe license state summarizer for diagnostic bundle. |
| **Diagnostic Utilities** | *None* | Scattered checks in `EnvironmentCheckResult`. | **MISSING** | Centralized diagnostic bundle builder, hardware/OS inspection, sanitized logs aggregator. | Create `DiagnosticCollector` and `DiagnosticBundleBuilder`. |
| **HealthSnapshotManager** | *None* | `AppHealthState` enum exists, but no subsystem prober. | **MISSING** | Health checks for core, voice, AI, Filmora, FFmpeg, database, disk. | Create `HealthSnapshotManager` and self-diagnostic command. |
| **SecretRedactor** | `licensing_server/services/support_service.py` | Basic regex matching for common keys. | **PARTIAL** | Missing local username path scrubbing, cookie scrubbing, database URL scrubbing. | Enhance regex patterns and path normalizer (`C:\Users\[USER]\...`). |
| **Telemetry** | `licensing_server/database.py` | `UpdateTelemetryDB` exists for update events. | **PARTIAL** | Dedicated crash telemetry and incident grouping model missing. | Create `IncidentDB` and diagnostic bundle endpoints. |

---

## 3. Immediate Action Plan

1. Implement `DiagnosticCollector`, `HealthSnapshotManager`, `PathNormalizer`, and `CrashSignatureGenerator` in `engine/deployment/diagnostic_collector.py`.
2. Enhance `runtime.py` with `GlobalExceptionHandler`, structured error levels (`INFO`, `WARNING`, `ERROR`, `CRITICAL`, `FATAL`), crash IDs (`JARVIS-CRASH-XXXXXX`), and safe mode loop detection (`>=3` consecutive failures).
3. Implement `engine/deployment/crash_reporter.py` with privacy-first local storage, consent settings, and offline retry queue.
4. Update `licensing_server/database.py` with `IncidentDB` and `DiagnosticRequestDB`.
5. Update `licensing_server/services/support_service.py` with incident grouping, remote diagnostic request/consent logic, and enhanced secret redaction.
6. Add UI overlays in `engine/commercial/ui_components.py` for crash recovery, safe mode, and customer support.
7. Execute test suite covering Golden Tests 1–20 and generate certification reports.
