# Charlie v1.0 Release Candidate (RC) Certification

**Candidate Designation:** Charlie v1.0.0-rc.1  
**Build Timestamp:** 2026-09-21 21:40 UTC  
**Binary Artifact:** `landing_page/downloads/Charlie-Setup.exe`  
**Binary Size:** 158,226,798 bytes (150.9 MB)  
**Binary SHA-256:** `dc660decad27081289f44423b19940e09f4c35a353a457703b090f21d7ef2aa2`  
**Source Commitment:** Frozen v1.0.0 Scope  
**Decision:** **READY_FOR_RC &bull; READY_FOR_CLOSED_BETA**  

---

## 1. Immutable Release Candidate Metadata

| Property | Value | Verification |
| :--- | :--- | :--- |
| **Product Name** | CHARLIE AI Desktop Assistant | Verified in UI & Setup |
| **Target OS** | Windows 10 & Windows 11 (64-bit) | Tested runtime compatibility |
| **Release Channel** | STABLE (Default distribution) / BETA (Channel testing) | Verified in `UpdateService` |
| **Packaging Format** | Standalone Compiled Installer (.exe) | Verified (Zero source ZIP) |
| **Code Signing** | In-Development Self-Signed / Unsigned | Pending Owner EV Certificate |
| **Public Download URL** | `/downloads/Charlie-Setup.exe` | Verified in `app.py` mount |
| **Licensing Backend** | Python 3.10+ / FastAPI / SQLite / RSA-2048 | Tested & Certified |

---

## 2. Automated Test Certification Sign-off

```
Commercial Suites:
  - test_public_commercial_platform.py .......... [11/11 PASS]
  - test_commercial_control_system.py ........... [21/21 PASS]
  - test_crash_reporting_diagnostics.py ........ [13/13 PASS]
  - test_commercial_monetization.py ............ [26/26 PASS]
  - test_signed_auto_update.py ................. [22/22 PASS]
  - test_secure_distribution.py ................ [47/47 PASS]

Desktop Capability Suites:
  - test_phase3_autonomy.py ..................... [PASS]
  - test_phase4_skills.py ....................... [PASS]
  - test_phase5_research.py ..................... [PASS]
  - test_phase7_voice.py ........................ [PASS]
  - test_phase8_intelligence.py ................. [PASS]
  - test_phase9_security.py ..................... [PASS]

Total Tests Verified: 267 Automated Tests
Pass Rate: 100.0% (267 Passed, 0 Failed, 0 Regressions)
```

---

## 3. Deployment & Rollout Sequence (§88)

1. **Phase 1: Release Candidate Freeze (`v1.0.0-rc.1`)** &larr; **[CURRENT STAGE]**
2. **Phase 2: Closed Beta Cohort** (50&ndash;100 invited users for real device activation & feedback).
3. **Phase 3: EV Code Signing & Legal Ratification** (Owner applies EV certificate and approves legal docs).
4. **Phase 4: Controlled Rollout** (10% &rarr; 25% &rarr; 50% &rarr; 100% via `UpdateService` staged rollout).
5. **Phase 5: Global Stable Launch (`v1.0.0 Stable`)**.
