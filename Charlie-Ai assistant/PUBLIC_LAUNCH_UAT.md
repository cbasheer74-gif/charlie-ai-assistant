# CHARLIE Public Commercial Platform — User Acceptance Testing (UAT)

**UAT Date:** 2026-09-21  
**Environment:** Windows 10/11 64-bit & Modern Web Browsers (Chrome, Edge, Firefox)  
**Target:** End-to-End Customer Journeys  
**Overall UAT Verdict:** PASS &bull; READY FOR STAGED COMMERCIAL PILOT  

---

## 1. Journey 1: Free Starter Customer

```
Visitor Lands on Website
  │
  ▼
Clicks "Start Free" / "Download Free"
  │
  ▼
Enters Name, Email, Password -> "Create Free Account"
  │
  ▼
Server registers user -> issues JWT + refresh tokens -> Default STARTER plan assigned
  │
  ▼
Downloads official CHARLIE-Setup.exe (151 MB, verified SHA-256)
  │
  ▼
Installs on Windows 10/11 -> Logs into desktop app
  │
  ▼
Desktop activates device -> Server grants Starter entitlement (10 active minutes/day)
  │
  ▼
Customer Portal reflects: Starter Plan, 1 Active PC, 10 min daily allowance
```
**Test Result:** **PASS** (Zero friction, no credit card asked).

---

## 2. Journey 2: Paid Subscription Customer (Premium ₹199/mo)

```
Visitor inspects Pricing Grid -> selects "Premium" (₹199 / mo)
  │
  ▼
Registers / Logs in with email & password
  │
  ▼
Client requests POST /payment/create-order -> Server computes 19,900 paise
  │
  ▼
Razorpay Checkout displays ₹199 -> Payment authorized
  │
  ▼
Server verifies HMAC-SHA256 signature -> marks PaymentDB VERIFIED
  │
  ▼
SubscriptionDB updated: Plan=PREMIUM, Status=ACTIVE, Expires=Now + 30 Days
  │
  ▼
User launches CHARLIE desktop -> Entitlement refreshed
  │
  ▼
Dual Neural Voices (Male + Female) & Deep Research immediately unlocked
```
**Test Result:** **PASS** (Server-side price authority enforced, no client tampering possible).

---

## 3. Journey 3: Lifetime License Customer (₹999 One-Time)

```
Visitor selects "Lifetime" (₹999 Pay Once · Own Forever)
  │
  ▼
Authenticated checkout -> Server creates order for 99,900 paise
  │
  ▼
Payment verified -> Server sets Status=LIFETIME_ACTIVE, expires_at=None
  │
  ▼
No recurring billing scheduled
  │
  ▼
User activates on Primary PC -> Entitlement issued with license_type: LIFETIME
  │
  ▼
User attempts concurrent activation on Second PC -> Blocked: DEVICE_CONFLICT
  │
  ▼
User clicks "Transfer License" in Customer Portal -> Old PC revoked, New PC activated
```
**Test Result:** **PASS** (One-Active-PC strictly enforced with clean transfer capability).

---

## 4. Journey 4: Customer Self-Service & Support Flow

- **Password Reset:** Request via `/auth/forgot-password` -> generates token -> `/auth/reset-password` updates password -> increments `session_version` -> revokes previous sessions. (**PASS**)
- **Billing Management:** Customer portal displays current plan, renewal date, and billing history. Recurring plans cancelable with 1 click. (**PASS**)
- **Support Ticket:** Customer submits ticket via `/support/api/tickets` -> integrated directly with Owner Support Center. Redacted crash logs attachable without leaking credentials. (**PASS**)
