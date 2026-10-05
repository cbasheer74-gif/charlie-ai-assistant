# CHARLIE Release Signing Key Rotation Runbook

**Standard Operating Procedure for Scheduled and Emergency Cryptographic Key Rotation.**

---

## 1. Overview & Policy

- **Key Algorithm:** RSA-2048 (e=65537) with PSS padding and SHA-256 digests.
- **Rotation Interval:** Annually (scheduled), or immediately upon suspected compromise.
- **Key Roles:**
  - **Private Signing Key:** Protected on build server/HSM (`entitlement_sign.pem`).
  - **Public Verification Key:** Embedded into desktop client (`entitlement_verify.pub`).

---

## 2. Emergency Key Rotation Procedure

If the RSA private key is suspected of exposure:

### Step 1: Pause All Active Release Channels
Immediately issue pause commands for all active releases across STABLE and BETA:
```http
POST /updates/releases/{version}/pause
```

### Step 2: Generate New RSA-2048 Keypair
Execute key generation in isolated offline environment:
```powershell
python -c "from licensing_server.config import ensure_rsa_keypair; ensure_rsa_keypair()"
```
This produces:
- `licensing_server/keys/entitlement_sign.pem` (Secure private key)
- `licensing_server/keys/entitlement_verify.pub` (New public key)

### Step 3: Dual-Sign Transition Period
1. Build emergency patch version containing the **new** public key in `entitlement_verifier.py`.
2. Sign the emergency patch manifest with the **old** key so existing installed clients can verify and install it.
3. Once clients upgrade to the emergency patch, all subsequent releases will be signed exclusively with the **new** key.

### Step 4: Revoke Compromised Key
1. Archive and securely wipe the old private key.
2. Publish public security disclosure and advisory to registered users via Customer Portal.
