# CHARLIE Crash Reporting & Remote Diagnostics — Privacy and Security Model

**Document Status:** Production Approved  
**Version:** 1.0.0  
**Classification:** Confidential — Architecture & Privacy Engineering

---

## 1. Privacy-By-Design Principles

CHARLIE operates as a commercial Windows desktop assistant with access to local system resources, user files, browser sessions, and connected tools. To maintain strict user privacy and enterprise-grade compliance:

1. **Zero Silent Remote Access:** Support staff or admins cannot initiate arbitrary shells, execute remote commands, browse directories, or capture screens without explicit customer action.
2. **Technical Telemetry Only:** Default diagnostic reports contain exclusively system metrics (OS, RAM, CPU architecture, free disk), module health states, app version, release channel, and sanitized exception stacks.
3. **Strict Ingestion Allowlist:**
   - Permitted: OS version, system architecture, module availability, license plan type, sanitized error logs, service health status.
   - Strictly Prohibited: User documents, code files, emails, chat history, audio recordings, camera feeds, cookies, passwords, private keys, authorization tokens.
4. **Consent Control Hierarchy:**
   - `ASK_EVERY_TIME` (Default): Requires user interaction before any report is transmitted.
   - `AUTO_SEND`: Automatically queues technical crash reports; never sends user documents or screenshots.
   - `NEVER_SEND`: Suppresses all remote uploads; retains local logs only.

---

## 2. Redaction Architecture (`SecretRedactor`)

The diagnostic pipeline runs automated scrubbing before writing to disk or transmitting to backend servers:

```
Raw Exception / Log String
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Pattern Redaction                                      │
│  - OpenAI / Anthropic Keys (sk-[a-zA-Z0-9_-]{20,})     │
│  - Google Gemini Keys (AIza[0-9A-Za-z\-_]{20,})        │
│  - Bearer Tokens (Bearer [A-Za-z0-9\-\._~+/]+=*)       │
│  - JWT Format (ey...ey...xxx)                          │
│  - Key-Value Credentials (password, secret, token)     │
│  - Database Connection Strings (postgres://, mysql://) │
│  - HTTP Cookie Headers                                 │
│  - PEM Private Keys (-----BEGIN...PRIVATE KEY-----)    │
└────────────────────────────────────────────────────────┘
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Path Anonymization                                     │
│  - Windows: C:\Users\<Username>\ -> C:\Users\[USER]\   │
│  - UNIX: /home/<Username>/ -> /home/[USER]/            │
└────────────────────────────────────────────────────────┘
          │
          ▼
Sanitized Technical Diagnostic Bundle
```

---

## 3. Remote Diagnostic Request Workflow

Support personnel troubleshooting a ticket cannot pull data arbitrarily. The workflow enforces user consent at every stage:

```
[Support Staff]
      │
      ▼ POST /api/support/tickets/{id}/request-diagnostics
[Licensing Server] ── Stores DiagnosticRequestDB (Status: PENDING)
      │
      ▼ Notification pushed to Customer Desktop / Web Portal
[Customer UI] ── Displays modal:
      │          "JARVIS Support requested a technical diagnostic report."
      │          Shows exact categories: [system_info, health, sanitized_logs]
      ├── User clicks "Decline" ──> Status: DECLINED (Zero data transmitted)
      └── User clicks "Review & Send"
                 │
                 ▼ Local Secret Scrubbing + Checksum Generation
                 ▼ Uploads bundle attached to Ticket ID
                 ▼ Status: APPROVED
```

---

## 4. Hardware Fingerprint Protection

- Raw hardware UUIDs, MAC addresses, and motherboard serial numbers are never stored in diagnostic logs.
- Client translates raw identifiers into a truncated cryptographic hash:
  $$\text{device\_id\_ref} = \text{SHA256}(\text{raw\_hardware\_id})[:12]$$
- Provides device transfer and duplicate troubleshooting capability without exposing hardware identifiers.

---

## 5. Storage Layout & Data Retention

Local diagnostics are stored under the user's isolated application directory (`AppData/CHARLIE/diagnostics/`):
- `crashes/`: Individual JSON crash events (`CHARLIE-CRASH-XXXXXX.json`)
- `bundles/`: Sanitized diagnostic bundles (`CHARLIE-CRASH-XXXXXX_bundle.json`)
- `logs/`: Rotated sanitized logs
- `queue/`: Pending uploads for offline-to-online retry
- `reports/`: Self-diagnosis snapshots

**Retention Limits:**
- Client-side maximum: 50 crash files or 30 days retention.
- Automated cleanup runs on every crash capture and startup.
