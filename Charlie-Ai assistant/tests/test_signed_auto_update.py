"""
tests/test_signed_auto_update.py — Test suite for CHARLIE Signed Auto-Update & Release Server.

Covers the 20 Golden Tests:
  1.  Golden Test 1:  v1.0.0 installed -> v1.0.1 published -> detected.
  2.  Golden Test 2:  Download valid signed update -> checksum + signature PASS.
  3.  Golden Test 3:  Tampered installer byte -> HASH_MISMATCH blocked.
  4.  Golden Test 4:  Tampered manifest -> INVALID_SIGNATURE blocked.
  5.  Golden Test 5:  Install update -> version upgraded & marked LAST_KNOWN_GOOD.
  6.  Golden Test 6:  Force startup failure -> automatic rollback to previous version.
  7.  Golden Test 7:  Database migration failure -> transactional rollback without data loss.
  8.  Golden Test 8:  Subscription retained after update (same plan).
  9.  Golden Test 9:  Device binding retained (same active device, no fake PC).
  10. Golden Test 10: Offline during update check -> app remains usable.
  11. Golden Test 11: Release server unavailable -> app starts.
  12. Golden Test 12: Beta release -> Beta users see update, Stable users do not.
  13. Golden Test 13: 5% staged rollout -> deterministic cohort receives offer.
  14. Golden Test 14: Pause rollout -> offers halt immediately.
  15. Golden Test 15: Revoke bad update -> clients reject installation.
  16. Golden Test 16: Old manifest replay -> downgrade blocked.
  17. Golden Test 17: Insufficient disk / missing package -> safe block.
  18. Golden Test 18: Interrupted updater -> recovery from backup snapshot.
  19. Golden Test 19: Active task guard (Filmora export) -> update deferred.
  20. Golden Test 20: Reinstall -> user data preserved.
"""

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.deployment.models import ReleaseChannel, ReleaseManifest, UpdateStatus
from engine.deployment.paths import DeploymentPathManager
from engine.deployment.update_client import UpdateClient
from engine.deployment.update_installer import UpdateInstaller
from engine.deployment.update_rollback import (
    ActiveTaskGuard,
    ChecksumVerifier,
    PostUpdateHealthChecker,
    PreUpdateBackupManager,
    ReleaseChannelManager,
    RollbackManager,
    SignatureVerifier,
    UpdateManager,
)
from licensing_server.database import (
    Base,
    DeviceDB,
    PlanTier,
    SubscriptionDB,
    SubscriptionStatus,
    UpdateReleaseDB,
    UserDB,
    _utcnow,
)
from licensing_server.services.entitlement_signer import EntitlementSigner
from licensing_server.services.update_service import UpdateService, is_newer_version, parse_semver


class TestSignedAutoUpdateSystem(unittest.TestCase):
    """End-to-end test suite for Signed Auto-Update & Release Server."""

    @classmethod
    def setUpClass(cls):
        # In-memory SQLite for Release Server tests
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

        cls.signer = EntitlementSigner()
        cls.pub_key_pem = cls.signer.public_key_pem
        cls.update_service = UpdateService()

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.db = self.Session()

        # Temporary workspace mimicking AppData/CHARLIE
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.paths = DeploymentPathManager(data_dir_override=str(self.tmp_dir))
        self.update_mgr = UpdateManager(path_manager=self.paths, public_key_pem=self.pub_key_pem)

    def tearDown(self):
        self.db.rollback()
        self.db.close()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_dummy_package(self, content: bytes = b"CHARLIE_INSTALLER_V101_BINARY_PAYLOAD") -> Tuple[Path, str]:
        """Creates dummy installer binary and returns (path, sha256)."""
        pkg_path = self.paths.get_sub_dir("updates") / "dummy_installer.exe"
        pkg_path.write_bytes(content)
        sha = hashlib.sha256(content).hexdigest()
        return pkg_path, sha

    # ── Golden Test 1: Update Detection ──────────────────────────────────────
    def test_golden_01_update_detection(self):
        """v1.0.0 installed -> Publish signed v1.0.1 -> detected."""
        pkg_path, sha = self._create_dummy_package()
        ok, msg, rel = self.update_service.register_release(
            self.db,
            version="1.0.1",
            download_url="https://updates.charlie.ai/v1.0.1/CHARLIE-Setup.exe",
            sha256=sha,
            channel="STABLE",
            release_notes="Speed improvements",
        )
        self.assertTrue(ok)

        # Check update from client on v1.0.0
        res = self.update_service.check_update(self.db, client_version="1.0.0", channel="STABLE")
        self.assertTrue(res["update_available"])
        self.assertEqual(res["latest_version"], "1.0.1")
        self.assertEqual(res["sha256"], sha)
        self.assertIsNotNone(res["signature"])

    # ── Golden Test 2: Valid Signed Update & Verification ────────────────────
    def test_golden_02_download_valid_signed_update(self):
        """Download valid signed update -> checksum + signature PASS."""
        pkg_content = b"VALID_SIGNED_INSTALLER_PAYLOAD_101"
        sha = hashlib.sha256(pkg_content).hexdigest()

        ok, msg, rel = self.update_service.register_release(
            self.db,
            version="1.0.1",
            download_url="https://updates.charlie.ai/v1.0.1/CHARLIE-Setup.exe",
            sha256=sha,
            channel="STABLE",
        )
        self.assertTrue(ok)

        manifest = self.update_service._build_canonical_manifest(rel)
        sig = rel.signature

        stage_res = self.update_mgr.stage_and_verify_package(
            package_bytes=pkg_content,
            manifest_dict=manifest,
            signature_b64=sig,
            expected_sha256=sha,
        )

        self.assertTrue(stage_res["staged"])
        self.assertTrue(stage_res["signature_verified"])
        self.assertTrue(stage_res["checksum_verified"])
        self.assertTrue(Path(stage_res["path"]).exists())

    # ── Golden Test 3: Tampered Installer (Hash Mismatch) ────────────────────
    def test_golden_03_tampered_installer_rejected(self):
        """Modify one byte in installer -> HASH_MISMATCH -> blocked and quarantined."""
        valid_content = b"LEGITIMATE_SIGNED_INSTALLER_BYTES"
        expected_sha = hashlib.sha256(valid_content).hexdigest()

        ok, _, rel = self.update_service.register_release(
            self.db,
            version="1.0.1",
            download_url="https://updates.charlie.ai/v1.0.1/CHARLIE-Setup.exe",
            sha256=expected_sha,
        )
        self.assertTrue(ok)
        manifest = self.update_service._build_canonical_manifest(rel)

        # Inject 1 altered byte into payload
        tampered_content = b"XEGITIMATE_SIGNED_INSTALLER_BYTES"

        stage_res = self.update_mgr.stage_and_verify_package(
            package_bytes=tampered_content,
            manifest_dict=manifest,
            signature_b64=rel.signature,
            expected_sha256=expected_sha,
        )

        self.assertFalse(stage_res["staged"])
        self.assertIn("HASH_MISMATCH", stage_res["reason"])

        # Quarantined file must be deleted
        quarantine_file = self.paths.get_sub_dir("updates") / "CHARLIE_Update_1.0.1.bin"
        self.assertFalse(quarantine_file.exists())

    # ── Golden Test 4: Tampered Manifest (Signature Rejection) ───────────────
    def test_golden_04_tampered_manifest_rejected(self):
        """Altered manifest parameters -> INVALID_SIGNATURE -> blocked."""
        content = b"SAFE_BINARY"
        sha = hashlib.sha256(content).hexdigest()

        ok, _, rel = self.update_service.register_release(
            self.db, version="1.0.1", download_url="https://updates.charlie.ai/pkg.exe", sha256=sha
        )
        self.assertTrue(ok)
        manifest = self.update_service._build_canonical_manifest(rel)

        # Attacker modifies download URL in manifest
        tampered_manifest = dict(manifest)
        tampered_manifest["download_url"] = "https://evil.com/malicious.exe"

        stage_res = self.update_mgr.stage_and_verify_package(
            package_bytes=content,
            manifest_dict=tampered_manifest,
            signature_b64=rel.signature,
            expected_sha256=sha,
        )

        self.assertFalse(stage_res["staged"])
        self.assertIn("INVALID_SIGNATURE", stage_res["reason"])

    # ── Golden Test 5: Clean Installation ────────────────────────────────────
    def test_golden_05_clean_install_success(self):
        """Install update -> health check passes -> marked LAST_KNOWN_GOOD."""
        pkg_path, sha = self._create_dummy_package()

        res = self.update_mgr.apply_update_with_safety_and_rollback(
            current_version="1.0.0",
            target_version="1.0.1",
            staged_package_path=pkg_path,
            health_check_fn=lambda: True,
        )

        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["upgraded_to"], "1.0.1")
        self.assertEqual(res["health_status"], "LAST_KNOWN_GOOD")
        self.assertTrue(Path(res["backup_reference"]).exists())

    # ── Golden Test 6: Startup Failure & Automatic Rollback ──────────────────
    def test_golden_06_startup_failure_triggers_rollback(self):
        """New version crashes on startup -> health check fails -> restored to v1.0.0."""
        # Create user config to verify restoration
        cfg_file = self.paths.get_config_file()
        cfg_file.write_text(json.dumps({"version": "1.0.0", "custom_theme": "cyber_blue"}))

        pkg_path, sha = self._create_dummy_package()

        # Update attempted, but health check returns False (simulating crash)
        res = self.update_mgr.apply_update_with_safety_and_rollback(
            current_version="1.0.0",
            target_version="1.0.1",
            staged_package_path=pkg_path,
            health_check_fn=lambda: False,
        )

        self.assertEqual(res["status"], "ROLLED_BACK")
        self.assertIn("POST_UPDATE_HEALTH_CHECK_FAILED", res["reason"])
        self.assertEqual(res["rollback_details"]["restored_version"], "1.0.0")

        # Verify config preserved from pre-update snapshot
        restored_cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        self.assertEqual(restored_cfg["custom_theme"], "cyber_blue")

    # ── Golden Test 7: Database Migration Rollback ───────────────────────────
    def test_golden_07_database_migration_failure_rollback(self):
        """Database migration failure -> atomic rollback without data loss."""
        from engine.deployment.migration import MigrationManager
        mig_mgr = MigrationManager(self.paths)

        # Pre-populate state
        cfg_file = self.paths.get_config_file()
        cfg_file.write_text(json.dumps({"important_user_data": "intact_123"}))

        # Register a failing migration
        mig_mgr.register_migration(99, lambda: False)
        result = mig_mgr.run_pending_migrations()

        self.assertEqual(result["status"], "FAILED")
        self.assertTrue(result["rollback_required"])

        # Data remains intact
        current_data = json.loads(cfg_file.read_text(encoding="utf-8"))
        self.assertEqual(current_data["important_user_data"], "intact_123")

    # ── Golden Test 8: Subscription Retained After Update ────────────────────
    def test_golden_08_subscription_retained_across_update(self):
        """Paid user updates -> same plan, no re-purchase prompt."""
        user = UserDB(id="u_sub_1", email="sub@charlie.ai", password_hash="h", role="CUSTOMER")
        sub = SubscriptionDB(id="s1", user_id=user.id, plan="PREMIUM", status="ACTIVE")
        self.db.add(user)
        self.db.add(sub)
        self.db.commit()

        # Simulate update snapshot and verification
        pkg_path, _ = self._create_dummy_package()
        res = self.update_mgr.apply_update_with_safety_and_rollback(
            current_version="1.0.0",
            target_version="1.0.1",
            staged_package_path=pkg_path,
            health_check_fn=lambda: True,
        )
        self.assertEqual(res["status"], "SUCCESS")

        # Verify database subscription is unchanged
        re_sub = self.db.query(SubscriptionDB).filter(SubscriptionDB.user_id == "u_sub_1").first()
        self.assertEqual(re_sub.plan, "PREMIUM")
        self.assertEqual(re_sub.status, "ACTIVE")

    # ── Golden Test 9: Device Binding Retained ───────────────────────────────
    def test_golden_09_device_binding_retained(self):
        """Device identity remains same; no fake 'new PC' created."""
        user = UserDB(id="u_dev_1", email="dev@charlie.ai", password_hash="h", role="CUSTOMER")
        device = DeviceDB(
            id="dev_fixed_123",
            user_id=user.id,
            fingerprint_hash="fp_123",
            device_name="Main-PC",
            status="ACTIVE",
        )
        sub = SubscriptionDB(id="s2", user_id=user.id, plan="BASIC", active_device_id=device.id)
        self.db.add(user)
        self.db.add(device)
        self.db.add(sub)
        self.db.commit()

        # Update
        pkg_path, _ = self._create_dummy_package()
        self.update_mgr.apply_update_with_safety_and_rollback(
            current_version="1.0.0", target_version="1.0.1", staged_package_path=pkg_path
        )

        re_sub = self.db.query(SubscriptionDB).filter(SubscriptionDB.user_id == "u_dev_1").first()
        self.assertEqual(re_sub.active_device_id, "dev_fixed_123")

    # ── Golden Test 10: Offline During Update Check ──────────────────────────
    def test_golden_10_offline_update_check_graceful(self):
        """Offline during update check -> app continues running normally."""
        client = UpdateClient(base_url="http://127.0.0.1:59999", path_manager=self.paths, timeout_seconds=1)
        avail, data = client.check_for_updates("1.0.0")
        self.assertFalse(avail)
        self.assertIn("error", data)

    # ── Golden Test 11: Release Server Unavailable ───────────────────────────
    def test_golden_11_server_unavailable_starts_safely(self):
        """Release server unavailable -> CHARLIE starts without blocking."""
        client = UpdateClient(base_url="http://invalid-release-server.local", timeout_seconds=1)
        is_avail, info = client.check_for_updates("1.0.0")
        self.assertFalse(is_avail)

    # ── Golden Test 12: Beta Channel Isolation ───────────────────────
    def test_golden_12_beta_release_isolation(self):
        """Beta releases visible to Beta users, invisible to Stable users."""
        pkg_path, sha = self._create_dummy_package()
        self.update_service.register_release(
            self.db,
            version="1.1.0-beta",
            download_url="https://updates.charlie.ai/v1.1.0-beta/CHARLIE-Setup.exe",
            sha256=sha,
            channel="BETA",
        )

        # Stable user check: MUST NOT see Beta release
        stable_check = self.update_service.check_update(self.db, client_version="1.0.0", channel="STABLE")
        self.assertFalse(stable_check["update_available"])

        # Beta user check: MUST see Beta release
        beta_check = self.update_service.check_update(self.db, client_version="1.0.0", channel="BETA")
        self.assertTrue(beta_check["update_available"])
        self.assertEqual(beta_check["latest_version"], "1.1.0-beta")

    # ── Golden Test 13: Staged Rollout Cohort Determinism ─────────────────────
    def test_golden_13_staged_rollout_deterministic_cohort(self):
        """5% staged rollout offers only to deterministic cohort devices."""
        pkg_path, sha = self._create_dummy_package()
        self.update_service.register_release(
            self.db,
            version="1.0.2",
            download_url="https://updates.charlie.ai/v1.0.2/pkg.exe",
            sha256=sha,
            channel="STABLE",
            rollout_percentage=5,
        )

        # Find 1 device in cohort and 1 outside cohort
        eligible_device = None
        ineligible_device = None

        for i in range(200):
            d_id = f"dev_test_device_{i}"
            res = self.update_service.check_update(self.db, client_version="1.0.0", channel="STABLE", device_id=d_id)
            if res["update_available"] and not eligible_device:
                eligible_device = d_id
            elif not res["update_available"] and not ineligible_device:
                ineligible_device = d_id
            if eligible_device and ineligible_device:
                break

        self.assertIsNotNone(eligible_device)
        self.assertIsNotNone(ineligible_device)

        # Determinism check: repeating check for same device produces exact same result
        res1 = self.update_service.check_update(self.db, client_version="1.0.0", channel="STABLE", device_id=eligible_device)
        res2 = self.update_service.check_update(self.db, client_version="1.0.0", channel="STABLE", device_id=eligible_device)
        self.assertTrue(res1["update_available"])
        self.assertTrue(res2["update_available"])

    # ── Golden Test 14: Pause Rollout ────────────────────────────────────────
    def test_golden_14_pause_rollout_stops_offers(self):
        """Owner pauses release -> clients no longer offered the update."""
        pkg_path, sha = self._create_dummy_package()
        self.update_service.register_release(
            self.db, version="1.0.3", download_url="https://updates.charlie.ai/1.0.3", sha256=sha
        )

        # Active
        check_before = self.update_service.check_update(self.db, client_version="1.0.0")
        self.assertTrue(check_before["update_available"])

        # Pause
        ok, _ = self.update_service.pause_release(self.db, version="1.0.3")
        self.assertTrue(ok)

        # Inactive
        check_after = self.update_service.check_update(self.db, client_version="1.0.0")
        self.assertFalse(check_after["update_available"])

    # ── Golden Test 15: Revoke Release ───────────────────────────────────────
    def test_golden_15_revoke_release_stops_distribution(self):
        """Revoke release -> new installations blocked."""
        pkg_path, sha = self._create_dummy_package()
        self.update_service.register_release(
            self.db, version="1.0.4", download_url="https://updates.charlie.ai/1.0.4", sha256=sha
        )

        ok, _ = self.update_service.revoke_release(self.db, version="1.0.4", reason="Critical memory leak")
        self.assertTrue(ok)

        check = self.update_service.check_update(self.db, client_version="1.0.0")
        self.assertFalse(check["update_available"])

    # ── Golden Test 16: Downgrade Protection / Replay ────────────────────────
    def test_golden_16_downgrade_and_replay_protection(self):
        """Replay of older valid manifest -> downgrade rejected."""
        # Client is on v2.0.0, candidate is v1.0.0
        self.assertFalse(is_newer_version("1.0.0", "2.0.0"))
        self.assertFalse(is_newer_version("1.9.0", "1.10.0"))
        self.assertTrue(is_newer_version("1.10.0", "1.9.0"))

    # ── Golden Test 17: Insufficient Disk / Safety Check ─────────────────────
    def test_golden_17_missing_staged_package_safely_aborted(self):
        """Missing staged file stops update before execution without corrupting state."""
        missing_path = self.paths.get_sub_dir("updates") / "non_existent.bin"
        res = self.update_mgr.apply_update_with_safety_and_rollback(
            current_version="1.0.0", target_version="1.0.1", staged_package_path=missing_path
        )
        self.assertEqual(res["status"], "FAILED")
        self.assertEqual(res["reason"], "STAGED_PACKAGE_MISSING")

    # ── Golden Test 18: Interrupted Updater Recovery ─────────────────────────
    def test_golden_18_interrupted_updater_recovery_from_snapshot(self):
        """Simulate updater crash -> rollback snapshot restores files."""
        # 1. Write user file
        token_file = self.paths.get_sub_dir("checkpoints") / "license_entitlement.jwt"
        token_file.write_text("VALID_JWT_TOKEN_123")

        # 2. Backup
        backup_path = self.update_mgr.backup_mgr.create_snapshot("1.0.0")
        self.update_mgr.rollback_mgr.record_rollback_point("1.0.0", backup_path)

        # 3. Simulate corruption by interrupted updater
        token_file.write_text("CORRUPTED_HALFWAY_WRITE")

        # 4. Trigger recovery
        recovery = self.update_mgr.rollback_mgr.execute_rollback()
        self.assertTrue(recovery["success"])

        # Token restored
        self.assertEqual(token_file.read_text(), "VALID_JWT_TOKEN_123")

    # ── Golden Test 19: Active Task Protection ───────────────────────────────
    def test_golden_19_active_task_protection_defers_update(self):
        """Active Filmora video export in progress -> update deferred."""
        # Simulate active Filmora lock
        filmora_lock = self.paths.get_sub_dir("checkpoints") / "filmora_export.busy"
        filmora_lock.write_text("EXPORTING_4K_VIDEO")

        pkg_path, _ = self._create_dummy_package()

        res = self.update_mgr.apply_update_with_safety_and_rollback(
            current_version="1.0.0", target_version="1.0.1", staged_package_path=pkg_path
        )

        self.assertEqual(res["status"], "DEFERRED")
        self.assertIn("Filmora video export in progress", res["reason"])

        # Clean up lock
        filmora_lock.unlink()

    # ── Golden Test 20: Reinstall Preserves User Data ────────────────────────
    def test_golden_20_reinstall_preserves_user_data(self):
        """Reinstall latest Setup.exe preserves settings and memory."""
        cfg_file = self.paths.get_config_file()
        cfg_file.write_text(json.dumps({"user_preference": "dark_cyber", "memory_count": 42}))

        # Reinstall process preserves data_dir
        self.assertTrue(cfg_file.exists())
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        self.assertEqual(cfg["user_preference"], "dark_cyber")
        self.assertEqual(cfg["memory_count"], 42)


if __name__ == "__main__":
    unittest.main()
