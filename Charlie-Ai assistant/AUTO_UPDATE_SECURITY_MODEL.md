# JARVIS Auto-Update Security Model & Threat Assessment

**Date:** 2026-09-21  
**Target:** Cryptographic Auto-Update, Release Server, and Delivery Pipeline  
**Standard:** Zero-Trust Binary Distribution & Cryptographic Authenticity  

---

## 1. Executive Summary

This document specifies the threat model and cryptographic defense architecture of the JARVIS Auto-Update and Release Delivery System. The system guarantees that no software update can execute or modify user binaries without valid RSA-2048 PSS signature verification and SHA-256 integrity checks, even if the release server or transport layer is compromised.

---

## 2. Threat Analysis & Implemented Controls

| Threat Scenario | Attack Vector | Implemented Security Control | Status |
|:---|:---|:---|:---:|
| **Man-in-the-Middle (MITM)** | Attacker intercepts network traffic to swap executable | HTTPS transport + asymmetric RSA-2048 PSS signature on manifest. Tampered binary rejected by SHA-256 check. | **PASS** |
| **Rogue / Compromised Server** | Attacker gains control of CDN or release server storage | Server compromise alone CANNOT distribute malware. Desktop verifies manifest signature against embedded RSA public key. | **PASS** |
| **Tampered Installer Binary** | Single byte modified in downloaded `.bin` / `.exe` | `ChecksumVerifier` computes SHA-256 chunk-by-chunk. Mismatch triggers immediate unlinking from quarantine. | **PASS** |
| **Forged Release Manifest** | Attacker constructs fake JSON with malicious URL | `SignatureVerifier` executes RSA-PSS SHA-256 verification. Unsigned or modified manifests fail immediately. | **PASS** |
| **Downgrade / Rollback Attack** | Attacker replays valid older manifest to re-introduce known flaw | `UpdateService` and client enforce strict SemVer monotonicity (`is_newer_version`). Lower versions are rejected. | **PASS** |
| **Compromised Admin Account** | Attacker compromises standard admin portal credentials | Admin account alone cannot forge cryptographic signatures without access to offline/HSM RSA private keys. | **PASS** |
| **Partial / Interrupted Install** | Power loss or network drop mid-installation | Multi-stage isolation: downloads remain in `.part` / quarantine; pre-update backup snapshot enables atomic restoration. | **PASS** |
| **Active Task Disruption** | Update kills app during active Filmora export or coding job | `ActiveTaskGuard` queries active lock files. Updates are deferred until heavy operations conclude. | **PASS** |
| **Privacy Leak in Telemetry** | Diagnostics transmitting sensitive user prompts | Telemetry is strictly anonymous: event type, client version, target version, channel, and salted device hash. | **PASS** |

---

## 3. Cryptographic Architecture

### 3.1 Asymmetric Key Separation
- **Private Signing Key (`entitlement_sign.pem`)**:
  - Resides exclusively on secure release server build infrastructure.
  - Never bundled in client distribution (`JARVIS.exe` or `dist/`).
  - Scanned and blocked by pre-build secret scanners in `build_production.py`.
- **Public Verification Key (`entitlement_verify.pub`)**:
  - Embedded into `entitlement_verifier.py` and `SignatureVerifier`.
  - Used strictly for read-only verification of manifest signatures.

### 3.2 Canonical Manifest Signing
Release manifests are normalized to canonical sorted JSON before signing:
```python
canonical_json = json.dumps(manifest_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
signature = private_key.sign(
    canonical_json,
    padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
    hashes.SHA256(),
)
```

### 3.3 Quarantine & Checksum Enforcement
All downloads are stored with temporary extensions in `AppData/JARVIS/updates/`. If `compute_sha256(file) != manifest.sha256`:
1. File is immediately deleted (`unlink`).
2. Error `HASH_MISMATCH` is logged.
3. Execution is prevented.

---

## 4. Verification Evidence
Covered and validated by 20 Golden Tests in [tests/test_signed_auto_update.py](file:///c:/Users/aney/Downloads/Charlie-main-1.0/Charlie-Ai%20assistant/tests/test_signed_auto_update.py):
- `test_golden_02_download_valid_signed_update`: PASS
- `test_golden_03_tampered_installer_rejected`: PASS
- `test_golden_04_tampered_manifest_rejected`: PASS
- `test_golden_16_downgrade_and_replay_protection`: PASS
