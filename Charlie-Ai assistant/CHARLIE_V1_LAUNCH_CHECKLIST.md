# Charlie v1.0 Public Commercial Launch Checklist

**Target:** Public Launch Gate  
**Build:** v1.0.0-rc.1  
**Status:** ALL ENGINEERING ITEMS VERIFIED &bull; GATED ON LEGAL & CODE SIGNING  

---

## 1. Engineering & Systems Checklist

- [x] **Desktop Core:** Text, Voice, Memory, Task Planner, Multi-Agent routing verified.
- [x] **Windows 10 Compatibility:** Runs cleanly on 64-bit Windows without developer tools.
- [x] **Distribution Security:** Official `Charlie-Setup.exe` (158 MB) verified; zero ZIP or source leaks.
- [x] **Website & Public Entry Point:** Landing page, responsive design, feature sections, FAQ operational.
- [x] **Pricing Integrity:** Starter, Basic (₹99), Premium (₹199), Advanced (₹299), Lifetime (₹999) enforced server-side.
- [x] **Secure Checkout:** Razorpay order creation, tamper rejection, HMAC verification, idempotency active.
- [x] **Licensing System:** One-Active-PC policy, authenticated license transfer, offline grace working.
- [x] **Customer Portal:** Self-service overview, billing management, device transfer, support tickets active.
- [x] **Owner Admin Dashboard:** KPI metrics, user search, suspension, refund tracking, incident overview operational.
- [x] **Auto-Update & Rollback:** Signed release manifests, SHA-256 verification, emergency pause, rollback ready.
- [x] **Support & Diagnostics:** Sanitized crash reporting, secret scrubbing, Safe Mode operational.
- [x] **Browser Hardening:** SecurityHeadersMiddleware (CSP, Nosniff, SAMEORIGIN, Referrer-Policy) active.

---

## 2. Business & Governance Checklist (Owner Action Items)

- [x] **Code Signing Pipeline:** Implemented in `scripts/sign_installer.py` & Inno `SignTool` with Authenticode fallback.
- [ ] **Live Gateway Credentials:** Switch Razorpay API keys from Test mode to live Merchant credentials when launching.
- [x] **Legal Disclosures:** Ratified `terms.html`, `privacy.html`, `refund.html`, `eula.html` to Official Release v1.0.
- [x] **Corporate Registration Details:** Entity name and postal address configured in `licensing_server/.env` and legal pages.
