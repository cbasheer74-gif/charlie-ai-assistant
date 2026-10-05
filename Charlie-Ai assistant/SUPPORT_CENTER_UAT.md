# CHARLIE Customer Support Center & Incident Management UAT

**Test Date:** 2026-09-21  
**Target Environment:** CHARLIE Desktop Assistant & Licensing Server  
**UAT Result:** 100% SUCCESS

---

## 1. User Acceptance Scenarios

### Scenario 1: Normal Crash Recovery Flow
1. **User Action:** Application encounters an unexpected exception while encoding a video clip.
2. **System Behavior:**
   - Exception caught by `GlobalExceptionHandler`.
   - Privacy-safe crash report saved in `AppData/CHARLIE/diagnostics/crashes/`.
   - Unique identifier `CHARLIE-CRASH-7F42A1` generated.
   - Application safely relaunches and displays `CrashRecoveryDialog`.
3. **User Choice:** User clicks **Send Diagnostic Report**.
4. **Backend Processing:**
   - Upload received at `/support/crash-report`.
   - Incident grouping engine matches stack signature: increments occurrence count on existing incident or registers `CRASH-001`.
   - Returns confirmation and incident reference.
5. **Outcome:** **PASS**

---

### Scenario 2: Startup Crash-Loop & Safe Mode
1. **User Action:** Faulty configuration or corrupt native DLL causes CHARLIE to fail 3 times consecutively during startup.
2. **System Behavior:**
   - `is_safe_mode_required()` evaluates to True (`consecutive_startup_failures >= 3`).
   - `AppHealthState.SAFE_MODE` activates.
   - Non-essential startup agents, heavy AI models, and third-party plugins are disabled.
   - User presented with `SafeModeDialog`: "CHARLIE started in Safe Mode because repeated startup failures were detected."
   - Options to Continue in Safe Mode, Restart Normally, or Contact Support.
3. **Outcome:** **PASS**

---

### Scenario 3: Customer Raises Support Ticket With Crash ID
1. **User Action:** Customer navigates to **Help & Support** tab, selects category "APP_CRASH", enters subject and description, and attaches crash ID `CHARLIE-CRASH-7F42A1`.
2. **System Behavior:**
   - Ticket `TICK-8B29E1` created in database.
   - Diagnostics attached to ticket.
   - All text sanitized: OpenAI keys, Gemini keys, user Windows paths redacted.
   - Support staff views ticket in Admin Dashboard with sanitized logs and environment metadata.
3. **Outcome:** **PASS**

---

### Scenario 4: Remote Technical Diagnostic Request
1. **Support Action:** Support engineer needs fresh health metrics to debug a licensing activation timeout.
2. **Workflow:**
   - Support clicks **Request Diagnostics** (`POST /api/support/tickets/{id}/request-diagnostics`).
   - Customer UI receives prompt: "CHARLIE Support requested a technical diagnostic report [system_info, health, sanitized_logs]".
   - Customer clicks **Review & Send**.
   - Bundle generated locally, scrubbed of all secrets, and uploaded directly to the ticket thread.
3. **Decline Validation:** When customer clicks **Decline**, server status transitions to `DECLINED` and zero bytes of telemetry are transmitted.
4. **Outcome:** **PASS**

---

### Scenario 5: Known Issues & Version Awareness
1. **Customer View:** Customer running v1.0.3 views **Known Issues**.
2. **System Behavior:**
   - Backend checks `IncidentDB` where workaround exists.
   - Customer sees notice: *"You are running v1.0.3 which has a known Filmora export issue. Workaround: Use FFmpeg fallback mode."*
3. **Outcome:** **PASS**
