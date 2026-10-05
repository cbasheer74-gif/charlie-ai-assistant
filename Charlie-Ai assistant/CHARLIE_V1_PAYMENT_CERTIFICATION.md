# Charlie v1.0 Payment & Revenue Architecture Certification

**Certification Date:** 2026-09-21  
**Build:** v1.0.0-rc.1  
**Target Gateway:** Razorpay Payment Gateway Abstraction (UPI, Cards, Netbanking, Wallets)  
**Status:** CERTIFIED &bull; SERVER-SIDE AUTHORITATIVE  

---

## 1. Commercial Pricing Tier Truth

| Plan | Catalog Currency | Paise (Smallest Unit) | Billing Cycle | Server Pricing Authority |
| :--- | :--- | :--- | :--- | :--- |
| **STARTER** | INR | 0 paise | Forever Free | Enforced (`Free / No Checkout`) |
| **BASIC** | INR | 9,900 paise (₹99) | 30 Days Recurring | Enforced |
| **PREMIUM** | INR | 19,900 paise (₹199) | 30 Days Recurring | Enforced |
| **ADVANCED** | INR | 29,900 paise (₹299) | 30 Days Recurring | Enforced |
| **LIFETIME** | INR | 99,900 paise (₹999) | One-time permanent | Enforced |

---

## 2. Verified Payment Invariants
1. **Server-Side Order Creation:** Browser cannot dictate pricing. `POST /payment/create-order` computes the exact paise amount based on the plan registry.
2. **Cryptographic Webhook & Signature Verification:** No payment is marked `VERIFIED` without verifying the HMAC-SHA256 signature using `RAZORPAY_KEY_SECRET`.
3. **Idempotency Guarantee:** Replay of identical payment IDs is detected and treated idempotently without duplicating revenue or resetting subscription expiration counters.
4. **Lifetime Decoupling:** Lifetime revenue is accurately distinguished from recurring Monthly Recurring Revenue (MRR) in the Owner Admin Dashboard.
5. **No Payment Secrets in Frontend:** Client bundle and landing page contain only `RAZORPAY_KEY_ID`.
6. **Grace Period & Expiration Handling:** When a recurring billing cycle lapses, user transitions to `GRACE_PERIOD` before falling back to `STARTER` without destroying user data.
