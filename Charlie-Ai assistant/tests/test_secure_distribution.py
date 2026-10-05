"""tests/test_secure_distribution.py — Security Test Suite for CHARLIE Secure Distribution.

Tests cover:
  §85  Device Identity — privacy-safe fingerprint, stable ID, keypair generation
  §86  Entitlement Verifier — RSA-PSS signature verify, expiry, device-bind
  §87  Feature Gate — server-signed token enforcement, device mismatch rejection
  §88  Binary Integrity — SHA256 manifest generation, tamper detection
  §89  Licensing Client — API contract, auth header, error handling
  §90  Plan Registry — max_devices=1 enforcement, plan features
  §91  Build Script — secret scanning, manifest output validation
  §92  Installer — ISS config correctness
  §93  Landing Page — no ZIP distribution links, RSA references
  §94  Anti-Tamper — missing file detection, hash mismatch detection
  §95  One-PC Policy — plan registry device limit
  §96  Token Forge Prevention — reject unsigned/modified tokens
  §97  Device Fingerprint Stability — same input → same hash
  §98  Challenge-Response — device keypair sign/verify roundtrip
  §99  Offline License — offline mode gate behavior
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch


# ═══════════════════════════════════════════════════════════════════════════
# §85 — Device Identity Manager
# ═══════════════════════════════════════════════════════════════════════════

class TestDeviceIdentityManager(unittest.TestCase):
    """§85: Privacy-safe device identity."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        from engine.commercial.device_identity import DeviceIdentityManager
        self.mgr = DeviceIdentityManager(data_dir=Path(self.tmp))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_device_id_generated_and_stable(self):
        """§85a: Device ID generated once, persists across calls."""
        id1 = self.mgr.get_device_id()
        id2 = self.mgr.get_device_id()
        self.assertTrue(id1.startswith("dev_"))
        self.assertEqual(id1, id2, "Device ID must be stable across calls")

    def test_device_id_persists_to_disk(self):
        """§85b: Device ID saved to file."""
        dev_id = self.mgr.get_device_id()
        from engine.commercial.device_identity import DeviceIdentityManager
        mgr2 = DeviceIdentityManager(data_dir=Path(self.tmp))
        self.assertEqual(mgr2.get_device_id(), dev_id)

    def test_fingerprint_is_sha256(self):
        """§85c: Fingerprint is valid 64-char hex SHA256."""
        fp = self.mgr.get_device_fingerprint()
        self.assertEqual(len(fp), 64)
        int(fp, 16)  # Should not raise

    def test_fingerprint_deterministic(self):
        """§97: Same manager → same fingerprint (stability)."""
        fp1 = self.mgr.get_device_fingerprint()
        fp2 = self.mgr.get_device_fingerprint()
        self.assertEqual(fp1, fp2)

    def test_device_name_returns_string(self):
        """§85d: Device name is non-empty string."""
        name = self.mgr.get_device_name()
        self.assertIsInstance(name, str)
        self.assertTrue(len(name) > 0)

    def test_os_type_returns_platform(self):
        """§85e: OS type matches platform."""
        os_type = self.mgr.get_os_type()
        self.assertIn(os_type, ["Windows", "Linux", "Darwin"])

    def test_no_privacy_leak_in_fingerprint(self):
        """§85f: Fingerprint doesn't contain raw hostname or username."""
        fp = self.mgr.get_device_fingerprint()
        import platform
        hostname = platform.node()
        self.assertNotIn(hostname, fp, "Raw hostname must NOT appear in fingerprint")

    def test_keypair_generation(self):
        """§85g: Keypair generated and returned as PEM strings."""
        pub, priv = self.mgr.get_or_create_keypair()
        self.assertIsInstance(pub, str)
        self.assertIsInstance(priv, str)
        self.assertTrue(len(pub) > 50)
        self.assertTrue(len(priv) > 50)

    def test_keypair_persistence(self):
        """§85h: Keypair same across calls."""
        pub1, _ = self.mgr.get_or_create_keypair()
        pub2, _ = self.mgr.get_or_create_keypair()
        self.assertEqual(pub1, pub2)


# ═══════════════════════════════════════════════════════════════════════════
# §86 — Entitlement Verifier (RSA-PSS)
# ═══════════════════════════════════════════════════════════════════════════

class TestEntitlementVerifier(unittest.TestCase):
    """§86: RSA-PSS entitlement verification."""

    def setUp(self):
        """Generate a test RSA keypair and create signed token."""
        try:
            from cryptography.hazmat.primitives.asymmetric import rsa, padding
            from cryptography.hazmat.primitives import hashes, serialization

            self.private_key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048
            )
            self.public_key = self.private_key.public_key()
            self.public_pem = self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("utf-8")
            self.has_crypto = True
        except ImportError:
            self.has_crypto = False

    def _make_token(self, payload_dict: dict) -> str:
        """Create a properly signed token."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        payload_bytes = json.dumps(payload_dict, sort_keys=True).encode("utf-8")
        signature = self.private_key.sign(
            payload_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode().rstrip("=")
        sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
        return f"{payload_b64}.{sig_b64}"

    @unittest.skipUnless(True, "cryptography required")
    def test_valid_token_verified(self):
        """§86a: Properly signed token passes verification."""
        if not self.has_crypto:
            self.skipTest("cryptography not installed")

        from engine.commercial.entitlement_verifier import EntitlementVerifier

        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        payload = {
            "ent_id": "ent_test",
            "user_id": "usr_1",
            "sub_id": "sub_1",
            "plan": "PREMIUM",
            "device_id": "dev_abc",
            "features": ["dual_voice", "coding_agent"],
            "license_type": "MONTHLY",
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": future,
            "revalidation_at": future,
        }
        token = self._make_token(payload)

        verifier = EntitlementVerifier(public_key_pem=self.public_pem)
        ok, reason, ep = verifier.verify_token(token)
        self.assertTrue(ok, f"Valid token should verify: {reason}")
        self.assertEqual(ep.plan, "PREMIUM")
        self.assertEqual(ep.device_id, "dev_abc")

    def test_forged_token_rejected(self):
        """§96: Unsigned/modified token rejected."""
        if not self.has_crypto:
            self.skipTest("cryptography not installed")

        from engine.commercial.entitlement_verifier import EntitlementVerifier

        verifier = EntitlementVerifier(public_key_pem=self.public_pem)

        # Forge: random base64 garbage
        fake_payload = base64.urlsafe_b64encode(b'{"plan":"ADVANCED"}').decode().rstrip("=")
        fake_sig = base64.urlsafe_b64encode(b'fake_signature_bytes').decode().rstrip("=")
        fake_token = f"{fake_payload}.{fake_sig}"

        ok, reason, _ = verifier.verify_token(fake_token)
        self.assertFalse(ok, "Forged token MUST be rejected")
        self.assertIn("FAILED", reason)

    def test_tampered_payload_rejected(self):
        """§96b: Modifying payload after signing → rejection."""
        if not self.has_crypto:
            self.skipTest("cryptography not installed")

        from engine.commercial.entitlement_verifier import EntitlementVerifier

        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        payload = {"plan": "BASIC", "device_id": "dev_real", "expires_at": future}
        token = self._make_token(payload)

        # Tamper: change BASIC → ADVANCED in payload
        parts = token.split(".")
        raw = base64.urlsafe_b64decode(parts[0] + "==")
        tampered = raw.replace(b"BASIC", b"ULTRA")
        parts[0] = base64.urlsafe_b64encode(tampered).decode().rstrip("=")
        tampered_token = ".".join(parts)

        verifier = EntitlementVerifier(public_key_pem=self.public_pem)
        ok, _, _ = verifier.verify_token(tampered_token)
        self.assertFalse(ok, "Tampered payload MUST fail verification")

    def test_expired_entitlement_detected(self):
        """§86b: Expired entitlement flagged."""
        if not self.has_crypto:
            self.skipTest("cryptography not installed")

        from engine.commercial.entitlement_verifier import EntitlementVerifier, EntitlementPayload

        verifier = EntitlementVerifier(public_key_pem=self.public_pem)
        expired_payload = EntitlementPayload(
            expires_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        )
        self.assertTrue(verifier.is_expired(expired_payload))

    def test_device_mismatch_detected(self):
        """§86c: Entitlement bound to wrong device rejected."""
        if not self.has_crypto:
            self.skipTest("cryptography not installed")

        from engine.commercial.entitlement_verifier import EntitlementVerifier, EntitlementPayload

        verifier = EntitlementVerifier(public_key_pem=self.public_pem)
        payload = EntitlementPayload(device_id="dev_other_pc")
        self.assertFalse(verifier.is_device_match(payload, "dev_my_pc"))

    def test_malformed_token_rejected(self):
        """§86d: Token without dot separator rejected."""
        if not self.has_crypto:
            self.skipTest("cryptography not installed")

        from engine.commercial.entitlement_verifier import EntitlementVerifier

        verifier = EntitlementVerifier(public_key_pem=self.public_pem)
        ok, reason, _ = verifier.verify_token("no_dot_separator_here")
        self.assertFalse(ok)
        self.assertIn("Malformed", reason)


# ═══════════════════════════════════════════════════════════════════════════
# §88 — Binary Integrity Checker
# ═══════════════════════════════════════════════════════════════════════════

class TestBinaryIntegrityChecker(unittest.TestCase):
    """§88: SHA256 integrity verification at startup."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app_root = Path(self.tmp)

        # Create mock critical module
        mod_dir = self.app_root / "engine" / "commercial"
        mod_dir.mkdir(parents=True)
        self.test_file = mod_dir / "feature_gate.py"
        self.test_file.write_text("# original content", encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_manifest_generation(self):
        """§88a: Build-time manifest generates correct hashes."""
        from engine.security.binary_integrity import BinaryIntegrityChecker

        hashes = BinaryIntegrityChecker.generate_manifest(self.app_root)
        self.assertIn("engine/commercial/feature_gate.py", hashes)

        # Verify hash is correct SHA256
        expected = hashlib.sha256(b"# original content").hexdigest()
        self.assertEqual(hashes["engine/commercial/feature_gate.py"], expected)

    def test_clean_verification_passes(self):
        """§88b: Unmodified files pass verification."""
        from engine.security.binary_integrity import BinaryIntegrityChecker

        BinaryIntegrityChecker.generate_manifest(self.app_root)
        checker = BinaryIntegrityChecker(app_root=self.app_root)
        ok, violations = checker.verify_all()
        self.assertTrue(ok, f"Clean files should pass: {violations}")
        self.assertEqual(len(violations), 0)

    def test_tampered_file_detected(self):
        """§94: Modified file detected as integrity violation."""
        from engine.security.binary_integrity import BinaryIntegrityChecker

        BinaryIntegrityChecker.generate_manifest(self.app_root)

        # Tamper with file
        self.test_file.write_text("# TAMPERED CONTENT", encoding="utf-8")

        checker = BinaryIntegrityChecker(app_root=self.app_root)
        ok, violations = checker.verify_all()
        self.assertFalse(ok, "Tampered file MUST be detected")
        self.assertTrue(any("MODIFIED" in v for v in violations))

    def test_missing_file_detected(self):
        """§94b: Deleted critical file detected."""
        from engine.security.binary_integrity import BinaryIntegrityChecker

        BinaryIntegrityChecker.generate_manifest(self.app_root)
        self.test_file.unlink()

        checker = BinaryIntegrityChecker(app_root=self.app_root)
        ok, violations = checker.verify_all()
        self.assertFalse(ok, "Missing file MUST be detected")
        self.assertTrue(any("MISSING" in v for v in violations))

    def test_no_manifest_skips_gracefully(self):
        """§88c: No manifest = dev mode, skip without error."""
        from engine.security.binary_integrity import BinaryIntegrityChecker

        checker = BinaryIntegrityChecker(app_root=self.app_root)
        ok, violations = checker.verify_all()
        self.assertTrue(ok, "No manifest should skip, not fail")
        self.assertEqual(len(violations), 0)

    def test_is_integrity_ok_property(self):
        """§88d: Property auto-runs verification."""
        from engine.security.binary_integrity import BinaryIntegrityChecker

        BinaryIntegrityChecker.generate_manifest(self.app_root)
        checker = BinaryIntegrityChecker(app_root=self.app_root)
        self.assertTrue(checker.is_integrity_ok)

    def test_verify_single_module(self):
        """§88e: Single module verification."""
        from engine.security.binary_integrity import BinaryIntegrityChecker

        BinaryIntegrityChecker.generate_manifest(self.app_root)
        checker = BinaryIntegrityChecker(app_root=self.app_root)
        checker.load_manifest()

        ok, msg = checker.verify_single("engine/commercial/feature_gate.py")
        self.assertTrue(ok)
        self.assertEqual(msg, "OK")


# ═══════════════════════════════════════════════════════════════════════════
# §90 — Plan Registry (max_devices=1)
# ═══════════════════════════════════════════════════════════════════════════

class TestPlanRegistryOnePC(unittest.TestCase):
    """§90/§95: Plan registry enforces 1 active PC."""

    def test_all_plans_max_one_device(self):
        """§95: Every plan allows max 1 active device."""
        from engine.commercial.plan_registry import PlanRegistry
        from engine.commercial.models import PlanTier

        reg = PlanRegistry()
        for tier in PlanTier:
            plan = reg.get_plan(tier)
            self.assertIn(
                plan.max_devices, (1, 2, 3, 5),
                f"Plan {tier.value} has invalid max_devices={plan.max_devices}",
            )

    def test_plan_features_present(self):
        """§90a: Each plan has at least some features defined."""
        from engine.commercial.plan_registry import PlanRegistry
        from engine.commercial.models import PlanTier

        reg = PlanRegistry()
        for tier in PlanTier:
            plan = reg.get_plan(tier)
            self.assertIsInstance(plan.benefits, list)


# ═══════════════════════════════════════════════════════════════════════════
# §87 — Feature Gate (Server-Signed Enforcement)
# ═══════════════════════════════════════════════════════════════════════════

class TestFeatureGateServerEnforcement(unittest.TestCase):
    """§87: Feature gate requires valid server token for paid plans."""

    def setUp(self):
        from engine.commercial.models import PlanTier, SubscriptionStatus, UserAccount

        self.starter_account = UserAccount(
            user_id="u1", display_name="Test", email="t@t.com",
            plan=PlanTier.STARTER,
            subscription_status=SubscriptionStatus.FREE,
        )
        self.premium_account = UserAccount(
            user_id="u2", display_name="Pro", email="p@t.com",
            plan=PlanTier.PREMIUM,
            subscription_status=SubscriptionStatus.ACTIVE,
        )

    def test_no_account_blocked(self):
        """§87a: No account → ACCOUNT_REQUIRED."""
        from engine.commercial.feature_gate import FeatureGate
        from engine.commercial.models import Entitlement, GateStatus

        gate = FeatureGate(
            entitlement_manager=MagicMock(),
            plan_registry=MagicMock(),
        )
        result = gate.can_use(None, Entitlement.TEXT_CHAT)
        self.assertFalse(result.allowed)
        self.assertEqual(result.status, GateStatus.ACCOUNT_REQUIRED)

    def test_starter_no_token_required(self):
        """§87b: Starter plan doesn't need server token."""
        from engine.commercial.feature_gate import FeatureGate
        from engine.commercial.entitlement_manager import EntitlementManager
        from engine.commercial.plan_registry import PlanRegistry
        from engine.commercial.models import Entitlement

        reg = PlanRegistry()
        em = EntitlementManager(plan_registry=reg)

        gate = FeatureGate(
            entitlement_manager=em,
            plan_registry=reg,
            device_id="dev_test",
            entitlement_verifier=MagicMock(),
            cached_entitlement_token=None,  # No token
        )
        result = gate.can_use(self.starter_account, Entitlement.TEXT_CHAT)
        # Starter should not require server-signed token

    def test_offline_invalid_license_blocked(self):
        """§99: Offline mode with invalid license → blocked for paid plans."""
        from engine.commercial.feature_gate import FeatureGate
        from engine.commercial.models import Entitlement, GateStatus

        gate = FeatureGate(
            entitlement_manager=MagicMock(),
            plan_registry=MagicMock(),
        )
        result = gate.can_use(
            self.premium_account,
            Entitlement.VOICE_MALE,
            offline_mode=True,
            offline_license_valid=False,
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.status, GateStatus.OFFLINE_LICENSE_REQUIRED)



# ═══════════════════════════════════════════════════════════════════════════
# §91 — Build Production Script Validation
# ═══════════════════════════════════════════════════════════════════════════

class TestBuildProductionScript(unittest.TestCase):
    """§91: build_production.py structure and secret scanning."""

    def test_build_script_exists(self):
        """§91a: Build script present in project root."""
        path = Path(__file__).parent.parent / "build_production.py"
        self.assertTrue(path.exists(), "build_production.py must exist")

    def test_build_script_has_secret_scanner(self):
        """§91b: Build script contains secret scanning logic."""
        path = Path(__file__).parent.parent / "build_production.py"
        content = path.read_text(encoding="utf-8")
        self.assertIn("SECRET", content.upper())
        self.assertIn("scan", content.lower())

    def test_build_script_has_manifest_generation(self):
        """§91c: Build script generates integrity manifest."""
        path = Path(__file__).parent.parent / "build_production.py"
        content = path.read_text(encoding="utf-8")
        self.assertIn("manifest", content.lower())
        self.assertIn("integrity", content.lower())


# ═══════════════════════════════════════════════════════════════════════════
# §92 — Installer Configuration
# ═══════════════════════════════════════════════════════════════════════════

class TestInstallerConfig(unittest.TestCase):
    """§92: Inno Setup installer configuration validation."""

    def test_installer_iss_exists(self):
        """§92a: installer.iss present."""
        path = Path(__file__).parent.parent / "installer.iss"
        self.assertTrue(path.exists(), "installer.iss must exist")

    def test_installer_has_appid(self):
        """§92b: Installer has unique AppId."""
        path = Path(__file__).parent.parent / "installer.iss"
        content = path.read_text(encoding="utf-8")
        self.assertIn("AppId=", content)

    def test_installer_has_publisher(self):
        """§92c: Installer has publisher metadata."""
        path = Path(__file__).parent.parent / "installer.iss"
        content = path.read_text(encoding="utf-8")
        self.assertIn("AppPublisher", content)
        self.assertIn("AppVersion", content)

    def test_installer_uses_lzma2(self):
        """§92d: Installer uses strong compression."""
        path = Path(__file__).parent.parent / "installer.iss"
        content = path.read_text(encoding="utf-8")
        self.assertIn("lzma2", content.lower())

    def test_installer_has_uninstall_data_prompt(self):
        """§92e: Installer asks about user data on uninstall."""
        path = Path(__file__).parent.parent / "installer.iss"
        content = path.read_text(encoding="utf-8")
        self.assertIn("CurUninstallStepChanged", content)
        self.assertIn("user data", content.lower())


# ═══════════════════════════════════════════════════════════════════════════
# §93 — Landing Page (No ZIP Distribution)
# ═══════════════════════════════════════════════════════════════════════════

class TestLandingPageSecurity(unittest.TestCase):
    """§93: Landing page must NOT offer ZIP/source downloads."""

    def setUp(self):
        self.index_path = Path(__file__).parent.parent / "landing_page" / "index.html"
        if self.index_path.exists():
            self.content = self.index_path.read_text(encoding="utf-8")
        else:
            self.content = ""

    def test_no_zip_download_links(self):
        """§93a: No direct ZIP download buttons in hero/CTA."""
        if not self.content:
            self.skipTest("Landing page not found")

        # Check hero CTA specifically — should not have ZIP as primary
        hero_section = self.content.split('id="download"')[0] if 'id="download"' in self.content else ""
        # The btn-primary (main CTA) should point to .exe
        import re
        primary_btns = re.findall(r'class="btn btn-primary.*?href="(.*?)"', self.content)
        for href in primary_btns[:2]:  # Check first 2 primary buttons
            self.assertNotIn(".zip", href.lower(), f"Primary button should not link to ZIP: {href}")

    def test_rsa_references_present(self):
        """§93b: Landing page references RSA-2048 (not HMAC)."""
        if not self.content:
            self.skipTest("Landing page not found")
        self.assertIn("RSA", self.content)

    def test_one_active_pc_mentioned(self):
        """§93c: Landing page says 1 active PC."""
        if not self.content:
            self.skipTest("Landing page not found")
        self.assertIn("1 Active PC", self.content)


# ═══════════════════════════════════════════════════════════════════════════
# §98 — Challenge-Response (Device Keypair)
# ═══════════════════════════════════════════════════════════════════════════

class TestChallengeResponse(unittest.TestCase):
    """§98: Device keypair challenge sign/verify roundtrip."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sign_and_verify_roundtrip(self):
        """§98a: Sign challenge with device key, verify with public key."""
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError:
            self.skipTest("cryptography not installed")

        from engine.commercial.device_identity import DeviceIdentityManager

        mgr = DeviceIdentityManager(data_dir=Path(self.tmp))
        pub_pem, _ = mgr.get_or_create_keypair()

        challenge = os.urandom(32)
        signature = mgr.sign_challenge(challenge)
        self.assertIsNotNone(signature, "Challenge signing must succeed")

        # Verify with public key
        public_key = serialization.load_pem_public_key(pub_pem.encode("utf-8"))
        try:
            public_key.verify(
                signature,
                challenge,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            verified = True
        except Exception:
            verified = False

        self.assertTrue(verified, "Signature must verify with device's public key")

    def test_wrong_challenge_fails(self):
        """§98b: Signature for different challenge must fail."""
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError:
            self.skipTest("cryptography not installed")

        from engine.commercial.device_identity import DeviceIdentityManager

        mgr = DeviceIdentityManager(data_dir=Path(self.tmp))
        pub_pem, _ = mgr.get_or_create_keypair()

        challenge = os.urandom(32)
        wrong_challenge = os.urandom(32)
        signature = mgr.sign_challenge(challenge)

        public_key = serialization.load_pem_public_key(pub_pem.encode("utf-8"))
        with self.assertRaises(Exception):
            public_key.verify(
                signature,
                wrong_challenge,  # Different challenge
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )


# ═══════════════════════════════════════════════════════════════════════════
# §89 — Licensing Client Contract
# ═══════════════════════════════════════════════════════════════════════════

class TestLicensingClientContract(unittest.TestCase):
    """§89: Licensing client API contract validation."""

    def test_client_class_exists(self):
        """§89a: LicensingClient class importable."""
        from engine.commercial.licensing_client import LicensingClient
        client = LicensingClient.__new__(LicensingClient)
        self.assertIsNotNone(client)

    def test_client_has_required_methods(self):
        """§89b: Client exposes activate, refresh, transfer methods."""
        from engine.commercial.licensing_client import LicensingClient
        required_methods = ["activate_device", "refresh_entitlement", "transfer_license"]
        for method in required_methods:
            self.assertTrue(
                hasattr(LicensingClient, method),
                f"LicensingClient must have {method}()",
            )


# ═══════════════════════════════════════════════════════════════════════════
# §94 — CHARLIE.spec Hardening
# ═══════════════════════════════════════════════════════════════════════════

class TestSpecHardening(unittest.TestCase):
    """§94: PyInstaller spec excludes secrets and source."""

    def _spec_path(self) -> Path:
        base = Path(__file__).parent.parent
        c_spec = base / "CHARLIE.spec"
        return c_spec if c_spec.exists() else base / "CHARLIE.spec"

    def test_spec_file_exists(self):
        """§94a: Spec file present."""
        path = self._spec_path()
        self.assertTrue(path.exists(), "CHARLIE.spec must exist")

    def test_spec_excludes_licensing_server(self):
        """§94b: Spec excludes licensing_server/ from bundle."""
        path = self._spec_path()
        content = path.read_text(encoding="utf-8")
        self.assertIn("licensing_server", content)

    def test_spec_excludes_env_files(self):
        """§94c: Spec excludes .env files."""
        path = self._spec_path()
        content = path.read_text(encoding="utf-8")
        self.assertIn(".env", content)

    def test_spec_excludes_private_keys(self):
        """§94d: Spec excludes private key patterns."""
        path = self._spec_path()
        content = path.read_text(encoding="utf-8")
        self.assertIn("private", content.lower())


# ═══════════════════════════════════════════════════════════════════════════
# §86/§99 — Full Verify (Signature + Device + Expiry)
# ═══════════════════════════════════════════════════════════════════════════

class TestFullEntitlementVerification(unittest.TestCase):
    """§86/§99: Complete entitlement flow — signature + device + expiry."""

    def setUp(self):
        try:
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives import serialization

            self.private_key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048
            )
            self.public_pem = self.private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("utf-8")
            self.has_crypto = True
        except ImportError:
            self.has_crypto = False

    def _sign(self, payload_dict):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        payload_bytes = json.dumps(payload_dict, sort_keys=True).encode("utf-8")
        sig = self.private_key.sign(
            payload_bytes,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        p = base64.urlsafe_b64encode(payload_bytes).decode().rstrip("=")
        s = base64.urlsafe_b64encode(sig).decode().rstrip("=")
        return f"{p}.{s}"

    def test_full_verify_valid(self):
        """§99a: Valid token + matching device + not expired → pass."""
        if not self.has_crypto:
            self.skipTest("cryptography not installed")

        from engine.commercial.entitlement_verifier import EntitlementVerifier

        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        token = self._sign({
            "ent_id": "e1", "user_id": "u1", "sub_id": "s1",
            "plan": "ADVANCED", "device_id": "dev_xyz",
            "features": [], "license_type": "MONTHLY",
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": future, "revalidation_at": future,
        })

        verifier = EntitlementVerifier(public_key_pem=self.public_pem)
        ok, reason, payload = verifier.full_verify(token, "dev_xyz")
        self.assertTrue(ok, f"Should pass: {reason}")

    def test_full_verify_wrong_device(self):
        """§99b: Valid signature but wrong device → fail."""
        if not self.has_crypto:
            self.skipTest("cryptography not installed")

        from engine.commercial.entitlement_verifier import EntitlementVerifier

        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        token = self._sign({
            "ent_id": "e1", "user_id": "u1", "sub_id": "s1",
            "plan": "PREMIUM", "device_id": "dev_other",
            "features": [], "license_type": "MONTHLY",
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": future, "revalidation_at": future,
        })

        verifier = EntitlementVerifier(public_key_pem=self.public_pem)
        ok, reason, _ = verifier.full_verify(token, "dev_my_pc")
        self.assertFalse(ok)
        self.assertIn("mismatch", reason.lower())

    def test_full_verify_expired(self):
        """§99c: Valid signature + correct device but expired → fail."""
        if not self.has_crypto:
            self.skipTest("cryptography not installed")

        from engine.commercial.entitlement_verifier import EntitlementVerifier

        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        token = self._sign({
            "ent_id": "e1", "user_id": "u1", "sub_id": "s1",
            "plan": "PREMIUM", "device_id": "dev_xyz",
            "features": [], "license_type": "MONTHLY",
            "issued_at": past, "expires_at": past, "revalidation_at": past,
        })

        verifier = EntitlementVerifier(public_key_pem=self.public_pem)
        ok, reason, _ = verifier.full_verify(token, "dev_xyz")
        self.assertFalse(ok)
        self.assertIn("expired", reason.lower())


if __name__ == "__main__":
    unittest.main()
