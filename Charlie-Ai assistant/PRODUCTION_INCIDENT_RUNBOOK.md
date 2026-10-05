# CHARLIE Production Incident Runbook

**Audience:** Site Reliability Engineering, Customer Support, and Product Engineering  
**Version:** 1.0.0  
**Effective Date:** 2026-09-21

---

## 1. Incident Severity Definitions

| Severity | Definition | Target Response Time | Actions |
| :--- | :--- | :--- | :--- |
| **SEV0** | Catastrophic security breach, data corruption, or global licensing auth failure. | < 15 minutes | Immediate Owner escalation, pause release rollout, publish emergency advisory. |
| **SEV1** | Major desktop crash-loop, broad startup failure, or widespread payment outage. | < 1 hour | Enable Safe Mode fallback recommendations, initiate patch hotfix, notify impacted users. |
| **SEV2** | Significant core feature failure (e.g. Filmora export crash, Voice STT degradation). | < 4 hours | Publish Known Issue workaround, link incoming customer tickets, prioritize next sprint. |
| **SEV3** | Minor UI glitch, localized edge-case error, or non-blocking diagnostic warning. | < 24 hours | Standard triage, assign engineering owner, fix in regular update cycle. |

---

## 2. Crash Incident Lifecycle

```
[New Crash Spike Detected]
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Step 1: Automated Grouping                             │
│ Check Admin Dashboard -> Incidents                     │
│ Verify Crash Signature, occurrences, & affected version│
└────────────────────────────────────────────────────────┘
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Step 2: Rollout Regression Check                       │
│ Did crash cluster start immediately after a release?   │
│ YES: Navigate to /admin/releases -> Set Status: PAUSED │
│ NO: Continue diagnostic triage                         │
└────────────────────────────────────────────────────────┘
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Step 3: Workaround & Customer Communication            │
│ Update Incident with temporary workaround              │
│ Status: INVESTIGATING -> MITIGATED                     │
│ Known Issue appears automatically in Customer Portal   │
└────────────────────────────────────────────────────────┘
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Step 4: Fix Release & Verification                     │
│ Engineer deploys signed patch (e.g. v1.0.5)            │
│ Update Incident: fixed_in_version = "1.0.5"            │
│ Status: RESOLVED -> CLOSED                             │
└────────────────────────────────────────────────────────┘
```

---

## 3. Remote Diagnostic Request Protocol

Support staff troubleshooting difficult tickets:
1. Open ticket in Admin Dashboard.
2. Select **Request Diagnostics**.
3. Choose categories: `[system_info, health, sanitized_logs]`.
4. The customer receives an interactive notification.
5. If customer approves: sanitized bundle attaches directly to ticket.
6. If customer declines: respect customer privacy; proceed with verbal or manual guidance.

---

## 4. Emergency Safe Mode Recovery Procedures

If a user reports an inescapable startup crash:
1. Advise user to launch CHARLIE in Safe Mode (or let the 3-strike crash detector trigger it automatically).
2. In Safe Mode:
   - Experimental plugins and third-party extensions are quarantined.
   - User navigates to **Help & Support -> Self-Diagnosis**.
   - User clicks **Generate Support Bundle** to export sanitized diagnostics.
   - User submits ticket or repairs installation.
