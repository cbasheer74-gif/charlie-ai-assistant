# CHARLIE Commercial Release Runbook

**Standard Operating Procedure (SOP) for Building, Signing, and Publishing Official Updates.**

---

## 1. Release Lifecycle Stages

```
1. BUILD & SCAN → 2. INTEGRITY MANIFEST → 3. CODE SIGNING → 4. BETA PUBLISH →
5. BETA VALIDATION → 6. STABLE PROMOTION → 7. STAGED ROLLOUT (5% → 25% → 50% → 100%)
```

---

## 2. Step-by-Step Procedure

### Stage 1: Build & Secret Scan
1. Ensure code repository working directory is clean.
2. Run production build script:
   ```powershell
   python build_production.py --version 1.0.1 --build-number 101
   ```
3. The build pipeline executes:
   - Automated scan for leaked secrets (Gemini, OpenAI, Razorpay, private keys).
   - Embedding of official RSA public key into client verifier.
   - PyInstaller executable compilation.
   - Inno Setup `CHARLIE-Setup.exe` compilation.

### Stage 2: Artifact Checksum & Manifest Generation
1. Compute SHA-256 of the generated installer:
   ```powershell
   CertUtil -hashfile dist\CHARLIE-Setup.exe SHA256
   ```
2. Construct canonical release manifest.

### Stage 3: RSA-2048 Manifest Signing
1. The server or CI signing pipeline signs the canonical JSON manifest with the offline/protected RSA private key.
2. Desktop code NEVER contains or accesses this private key.

### Stage 4: Publish to Beta Channel
1. Register release via Admin Portal or API:
   ```http
   POST /updates/releases
   Content-Type: application/json
   X-Admin-Key: <SECURE_KEY>

   {
     "version": "1.0.1",
     "channel": "BETA",
     "download_url": "https://updates.charlie.ai/v1.0.1/CHARLIE-Setup.exe",
     "sha256": "<COMPUTED_HASH>",
     "release_notes": "Phase 15 auto-update stabilization"
   }
   ```
2. Beta cohort devices immediately detect and test the update.

### Stage 5: Beta Validation Window (24–48 Hours)
- Monitor crash rates and telemetry events via `GET /admin/api/metrics`.
- If zero critical issues arise, proceed to Stable.

### Stage 6: Promote to Stable & Staged Rollout
1. **5% Canary Cohort:**
   ```http
   POST /updates/releases/1.0.1/rollout
   {"rollout_percentage": 5}
   ```
2. Monitor crash reporting for 12 hours.
3. **25% Cohort:**
   ```http
   POST /updates/releases/1.0.1/rollout
   {"rollout_percentage": 25}
   ```
4. **50% Cohort:**
   ```http
   POST /updates/releases/1.0.1/rollout
   {"rollout_percentage": 50}
   ```
5. **100% General Availability:**
   ```http
   POST /updates/releases/1.0.1/rollout
   {"rollout_percentage": 100}
   ```
