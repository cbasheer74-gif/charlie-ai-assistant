# CHARLIE Public Commercial Platform Audit

**Audit Date:** 2026-09-21  
**Target:** CHARLIE Public Commercial Entry Point & Web Stack

---

## 1. Executive Summary

Evaluation of existing landing page, client scripts, commercial backend, authentication, checkout flows, and release distribution for production launch readiness.

---

## 2. Component Capability Matrix

| Component | Existing Location | Status | Reuse/Fix/Create | Security Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Landing Page UI** | `landing_page/index.html` | **PASS** | Reuse & enhance | Rich responsive UI, Plus Jakarta Sans, SVG branding. Needs real auth hooks and checkout integration. |
| **Pricing Display** | `landing_page/index.html` | **PASS** | Reuse | Correctly displays Starter (Free), Basic (₹99), Premium (₹199), Advanced (₹299), Lifetime (₹999). |
| **Plan Registry** | `engine/commercial/plan_registry.py` & `licensing_server/services/payment_service.py` | **PASS** | Reuse | Server-side authoritative prices (`PLAN_PRICES`) match desktop. |
| **Authentication Backend** | `licensing_server/services/auth_service.py` & `routes/auth.py` | **PASS** | Extend | Bcrypt hashing, JWT tokens, session versioning. Needs password reset and email verification endpoints. |
| **Authentication UI** | `landing_page/script.js` | **PARTIAL** | Fix | Currently uses mock timeout; hook to real `POST /auth/login` and `POST /auth/register`. |
| **Secure Checkout Backend** | `licensing_server/services/payment_service.py` | **PARTIAL** | Extend | Has signature verification & replay idempotency. Needs server-side `create-order` endpoint. |
| **Checkout UI** | *None* | **MISSING** | Create | Add secure checkout modal for plan selection and payment handling. |
| **Download Center** | `landing_page/downloads/CHARLIE-Setup.exe` | **PASS** | Reuse | 158 MB official compiled installer already present; no source ZIP. |
| **Customer Portal** | `licensing_server/routes/portal.py` | **PASS** | Reuse | Active PC view, license deactivation, transfer, and billing history. |
| **Admin Dashboard** | `licensing_server/routes/admin.py` | **PASS** | Reuse | Comprehensive owner control over users, devices, revenue, and releases. |
| **Support Center** | `licensing_server/routes/support.py` | **PASS** | Reuse | Ticket creation, crash report ingestion, incident grouping. |
| **Legal Pages** | *None* | **MISSING** | Create | Need Terms, Privacy, Refund, EULA, Security, and Contact pages with `DRAFT_REQUIRES_REVIEW` status. |
| **Security Headers** | `licensing_server/app.py` | **PARTIAL** | Extend | Add CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy middleware. |

---

## 3. Implementation Blueprint

1. Extend `AuthService` with password reset tokens (`POST /auth/forgot-password`, `POST /auth/reset-password`) and email verification (`POST /auth/verify-email`).
2. Extend `PaymentService` with server-side order creation (`POST /payment/create-order`) enforcing exact plan prices (₹99, ₹199, ₹299, ₹999 in paise).
3. Mount landing page and downloads in `licensing_server/app.py` with security headers.
4. Hook landing page JavaScript (`script.js`) to live API endpoints for auth, checkout, and download.
5. Generate draft legal pages (`terms.html`, `privacy.html`, `refund.html`, `eula.html`, `security.html`, `contact.html`).
6. Execute automated test suite covering all commercial flows and generate launch certification.
