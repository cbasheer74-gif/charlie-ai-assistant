# Charlie v1.0 Licensing & Device Binding Certification

**Certification Date:** 2026-09-21  
**Build:** v1.0.0-rc.1  
**Scope:** One-Active-PC Policy, RSA Entitlement Tokens, Device Transfer, Offline Grace  
**Status:** CERTIFIED &bull; ZERO PIRACY TOLERANCE  

---

## 1. One-Active-PC Policy Invariant

> **Rule:** Every paid subscription (Basic, Premium, Advanced, Lifetime) permits execution on **one active computer at a time**.

### Verified Enforcement Mechanisms:
1. **Device Fingerprint Binding:** Hardware binding uses a privacy-safe SHA-256 salted hash of system properties. Raw MAC addresses and hardware serials are never collected.
2. **Concurrent Activation Block:** When User attempts to activate a second machine while PC-1 is active, the server returns `DEVICE_CONFLICT` with active device details.
3. **Authenticated License Transfer:** User can transfer the active seat to the new PC via the Customer Portal or desktop login. Upon transfer, PC-1 is marked `DEACTIVATED` and its next refresh drops features to Starter.
4. **Offline Grace Policy:**
   - Monthly Plans: 14 days offline grace before mandatory revalidation.
   - Lifetime Plans: 90 days offline grace before background heartbeat check.
5. **Anti-Tampering:** Local SQLite caches and entitlement tokens are digitally signed with an RSA-2048 private key held exclusively by the licensing server. Local clock roll-back attempts are detected and rejected.
