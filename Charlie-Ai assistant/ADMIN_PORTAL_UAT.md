# CHARLIE Commercial Platform — User Acceptance Testing (UAT) Report

**Date:** 2026-09-21  
**Target:** Owner Admin Dashboard + Customer Self-Service Portal  
**Evaluation Scope:** 11 Target Personas Across End-to-End Workflows  
**Testing Framework:** Automated Verification + Real Database Simulation  

---

## 1. Executive Summary

This document verifies user acceptance testing (UAT) across the 11 defined commercial personas for CHARLIE. Every persona was simulated against the active SQLite database schema, licensing API endpoints, and client-side commercial core.

---

## 2. Persona Acceptance Scenarios & Results

### Persona 1: Platform Owner (`OWNER`)
- **Profile:** Executive account holder with unrestricted administrative rights.
- **Workflow:**
  1. Access `GET /admin` dashboard.
  2. Inspect real-time financial metrics: Total MRR (recurring only), gross revenue, lifetime purchases, active subscribers.
  3. Export sanitized financial and user audit data to CSV.
  4. View and filter global security alerts (tampering attempts, suspicious device count).
- **Observed Result:** Owner dashboard displays real-time SQLite data without placeholders; Lifetime sales (₹999) correctly excluded from MRR; exports sanitize password hashes.
- **Status:** **PASS**

---

### Persona 2: Operations Administrator (`ADMIN`)
- **Profile:** Operations manager managing user plans, device states, and account status.
- **Workflow:**
  1. Search for customer by email, name, or subscription ID.
  2. Suspend a rogue user with an audited reason.
  3. Reset an active device slot for a verified customer whose machine was reformatted.
  4. Grant temporary or promotional entitlements.
- **Observed Result:** Actions execute with audit logging (`AuditLogDB`); suspended user immediately has session version incremented and device unlinked; cannot perform Owner-only configuration changes.
- **Status:** **PASS**

---

### Persona 3: Technical Support Agent (`SUPPORT`)
- **Profile:** Support staff handling customer tickets, diagnostic reviews, and device unbinds.
- **Workflow:**
  1. View support tickets queued across categories (`LOGIN`, `PAYMENT`, `APP_CRASH`, etc.).
  2. Review customer diagnostic logs (safe, redacted of API keys and passwords).
  3. Add staff internal notes visible only to fellow team members.
  4. Reply to customer and transition ticket state from `OPEN` to `RESOLVED`.
- **Observed Result:** Internal notes are strictly excluded from customer API responses; diagnostics contain zero sensitive tokens; support staff cannot view raw payment credentials or signing keys.
- **Status:** **PASS**

---

### Persona 4: Free Starter User (`STARTER`)
- **Profile:** User exploring CHARLIE on the free tier.
- **Workflow:**
  1. Register account via customer portal.
  2. Access customer overview (`GET /me`).
  3. View 10-minute daily voice and desktop automation quota status.
  4. Browse available subscription plans on pricing page.
- **Observed Result:** Daily quota correctly displayed; locked features prompt upgrade without UI crash; no active license token required.
- **Status:** **PASS**

---

### Persona 5: Basic Plan Subscriber (`BASIC` — ₹99/month)
- **Profile:** Entry-level paying subscriber on recurring monthly billing.
- **Workflow:**
  1. Complete ₹99 checkout via payment gateway.
  2. Webhook triggers `activate_subscription`.
  3. Active PC registers single-seat license.
  4. Feature gate unlocks Basic tier capabilities (standard voice & automation).
- **Observed Result:** Plan correctly reflected in portal; next renewal date set to 30 days ahead; MRR increases by ₹99.
- **Status:** **PASS**

---

### Persona 6: Premium Plan Subscriber (`PREMIUM` — ₹199/month)
- **Profile:** Intermediate paying subscriber on recurring monthly billing.
- **Workflow:**
  1. Upgrade from Basic to Premium.
  2. Difference paid; new entitlement generated and RSA-2048 signed.
  3. Client instantly recognizes new capabilities without requiring reinstallation.
- **Observed Result:** Feature gate immediately enables Filmora video automations and advanced research features; MRR increases accordingly.
- **Status:** **PASS**

---

### Persona 7: Advanced Plan Subscriber (`ADVANCED` — ₹299/month)
- **Profile:** Top-tier recurring power user.
- **Workflow:**
  1. Subscribe to Advanced plan.
  2. Cloud AI allowance and priority concurrency unlocked.
  3. View active device status and billing receipts in customer portal.
- **Observed Result:** Full feature set unlocked; billing history displays verified payment references.
- **Status:** **PASS**

---

### Persona 8: Lifetime License Purchaser (`LIFETIME` — ₹999 one-time)
- **Profile:** Customer purchasing permanent access with no recurring subscription.
- **Workflow:**
  1. Purchase Lifetime package for ₹999.
  2. View customer portal dashboard.
  3. Verify renewal date is hidden ("No Renewal — Permanent Access").
  4. Verify MRR calculation in Owner admin view.
- **Observed Result:** Portal displays permanent access banner; Owner financial metrics show ₹999 in gross and lifetime revenue, but **₹0 added to MRR**.
- **Status:** **PASS**

---

### Persona 9: Cancelled Subscriber (`CANCELLED`)
- **Profile:** Subscriber who cancelled recurring renewal before period expiration.
- **Workflow:**
  1. Customer selects "Cancel Subscription" in portal.
  2. Status transitions to `CANCEL_AT_PERIOD_END`.
  3. Access continues until `expires_at` date.
  4. Upon expiration, account smoothly moves to Starter tier without deleting local user files.
- **Observed Result:** Clear cancellation confirmation shown without dark UX patterns; local user configurations and workspaces remain completely intact.
- **Status:** **PASS**

---

### Persona 10: Customer Replacing PC (License Transfer)
- **Profile:** Customer whose primary laptop was replaced or upgraded.
- **Workflow:**
  1. Customer logs into portal from new PC.
  2. Portal detects existing active PC slot is occupied.
  3. Customer initiates "Transfer License to This PC".
  4. Server unbinds old device and binds new device.
  5. Old device queries server and automatically reverts to Starter tier.
- **Observed Result:** One-active-PC policy strictly enforced; transfer history audited; old PC loses paid entitlement while local files remain safe.
- **Status:** **PASS**

---

### Persona 11: Customer with Failed Payment (`PAST_DUE` / `GRACE_PERIOD`)
- **Profile:** Subscriber whose card or recurring mandate failed renewal.
- **Workflow:**
  1. Webhook signals payment failure or subscription past due.
  2. System initiates 3-day grace period.
  3. Portal alerts user: "Payment Failed — Update payment method to retain paid features".
  4. If unresolved after grace period, account downgrades to Starter.
- **Observed Result:** User notified cleanly without immediate abrupt lock-out; financial ledger records failure without inflating revenue.
- **Status:** **PASS**

---

## 3. Persona Acceptance Summary Matrix

| Persona | Primary Function Tested | Acceptance Criteria | Result |
|:---|:---|:---|:---:|
| **1. Owner** | Revenue analytics, security alerts, CSV export | Accurate MRR (no Lifetime), zero placeholders | **PASS** |
| **2. Admin** | User suspension, device reset, plan grant | Audited changes, immediate session revocation | **PASS** |
| **3. Support Agent** | Ticket response, diagnostics, internal notes | Strict secret redaction, notes hidden from user | **PASS** |
| **4. Starter User** | Daily quota, upgrade prompt | Clean quota meter, non-blocking fallback | **PASS** |
| **5. Basic User** | ₹99 monthly recurring, single PC bind | 1 PC enforced, renewal date shown | **PASS** |
| **6. Premium User** | ₹199 monthly, in-place upgrade | In-place entitlement update without reinstall | **PASS** |
| **7. Advanced User** | ₹299 monthly, full capability | High concurrency, all feature gates unlocked | **PASS** |
| **8. Lifetime User** | ₹999 one-time purchase | Zero renewal date, excluded from MRR | **PASS** |
| **9. Cancelled User** | Cancel at period end | Access till expiry, no file deletion | **PASS** |
| **10. PC Replacer** | License transfer between devices | Old device revoked, new PC activated | **PASS** |
| **11. Failed Payment** | Grace period and failure notification | Non-punitive grace period, failed payment alert | **PASS** |

---

## 4. Conclusion
All 11 user personas have passed end-to-end user acceptance testing with 100% compliance against commercial specifications.
