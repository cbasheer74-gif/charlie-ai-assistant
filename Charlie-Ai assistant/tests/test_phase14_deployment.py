"""
CHARLIE Phase 14: Production Deployment & Lifecycle Test Suite
Verifies clean installation, onboarding resume, single-instance enforcement,
crash-loop safe mode, update verification, pre-backup rollback, and uninstallation.
"""

import hashlib
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.deployment.models import (
    AppHealthState,
    BuildInfo,
    EnvironmentType,
    InstallMode,
    OnboardingStep,
    ReleaseChannel,
    ReleaseManifest,
    TelemetryLevel,
)
from engine.deployment.paths import DeploymentPathManager, PortManager
from engine.deployment.runtime import (
    CharlieUserAgent,
    CrashManager,
    JarvisUserAgent,
    SingleInstanceManager,
    StartupManager,
    WindowsServiceManager,
)
from engine.deployment.onboarding import (
    FirstRunManager,
    OnboardingEngine,
    TelemetryConsentManager,
)
from engine.deployment.migration import MigrationManager
from engine.deployment.update_rollback import (
    CodeSigningManager,
    ReleaseChannelManager,
    RollbackManager,
    UpdateManager,
)
from engine.deployment.packaging import (
    BuildManager,
    EnvironmentValidator,
    InstallerBuilder,
    UninstallManager,
)
from engine.deployment.core import DeploymentPlatform
from actions.deployment_control import DeploymentControlActions


class TestPhase14Deployment(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.platform = DeploymentPlatform(data_dir_override=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_clean_install_and_paths(self):
        """Test stable user data paths and directory creation."""
        paths = self.platform.paths
        self.assertTrue(paths.data_dir.exists())
        self.assertTrue((paths.data_dir / "memory").exists())
        self.assertTrue((paths.data_dir / "graph").exists())
        self.assertTrue((paths.data_dir / "plugins").exists())
        self.assertTrue((paths.data_dir / "skills").exists())
        self.assertTrue((paths.data_dir / "backups").exists())
        self.assertTrue((paths.data_dir / "logs").exists())
        self.assertTrue((paths.data_dir / "checkpoints").exists())
        self.assertTrue((paths.data_dir / "updates").exists())
        self.assertTrue((paths.data_dir / "diagnostics").exists())

    def test_02_first_run_detection(self):
        """Test detection of fresh install vs recorded version."""
        first_run = self.platform.first_run_mgr
        self.assertTrue(first_run.is_first_run())

        first_run.record_installed_version("1.0.0", 100)
        self.assertFalse(first_run.is_first_run())

        # Test upgrade detection
        upgrade_info = first_run.check_upgrade("1.1.0", 110)
        self.assertTrue(upgrade_info["is_upgrade"])
        self.assertEqual(upgrade_info["previous_version"], "1.0.0")

    def test_03_onboarding_progression_and_resume(self):
        """Test step-by-step onboarding, interruption, and resumption."""
        onboarding = self.platform.onboarding_engine
        self.assertEqual(onboarding.get_next_pending_step(), OnboardingStep.WELCOME)

        # Complete Welcome
        onboarding.complete_step(OnboardingStep.WELCOME)
        self.assertEqual(onboarding.get_next_pending_step(), OnboardingStep.PRIVACY)

        # Complete Privacy with data
        onboarding.complete_step(OnboardingStep.PRIVACY, {"privacy_mode": "LOCAL"})
        self.assertEqual(onboarding.profile.privacy_mode, "LOCAL")
        self.assertEqual(onboarding.get_next_pending_step(), OnboardingStep.AI_PROVIDER)

        # Simulate interruption & reload
        new_onboarding = OnboardingEngine(self.platform.paths)
        self.assertEqual(new_onboarding.get_next_pending_step(), OnboardingStep.AI_PROVIDER)
        self.assertEqual(new_onboarding.profile.privacy_mode, "LOCAL")

    def test_04_onboarding_step_skipping(self):
        """Test skipping optional steps."""
        onboarding = self.platform.onboarding_engine
        onboarding.complete_step(OnboardingStep.WELCOME)
        onboarding.complete_step(OnboardingStep.PRIVACY)
        onboarding.complete_step(OnboardingStep.AI_PROVIDER)

        # Skip LOCAL_AI
        onboarding.skip_step(OnboardingStep.LOCAL_AI)
        self.assertIn("LOCAL_AI", onboarding.profile.skipped_steps)
        self.assertEqual(onboarding.get_next_pending_step(), OnboardingStep.VOICE)

    def test_05_first_safe_task_verification(self):
        """Test executing and verifying the first safe task."""
        onboarding = self.platform.onboarding_engine
        res = onboarding.verify_first_safe_task("Open Notepad and type Hello CHARLIE")
        self.assertEqual(res["status"], "PASS")
        self.assertTrue(res["screen_verified"])
        self.assertTrue(onboarding.profile.first_task_verified)

    def test_06_hardware_model_recommendation(self):
        """Test RAM-based local model sizing recommendations."""
        onboarding = self.platform.onboarding_engine
        self.assertEqual(onboarding.recommend_local_model(32.0)["tier"], "LARGE")
        self.assertEqual(onboarding.recommend_local_model(16.0)["tier"], "MEDIUM")
        self.assertEqual(onboarding.recommend_local_model(8.0)["tier"], "SMALL")
        self.assertEqual(onboarding.recommend_local_model(4.0)["tier"], "TINY")

    def test_07_single_instance_lock(self):
        """Test mutex lock acquisition and duplicate instance blocking."""
        mgr1 = SingleInstanceManager(self.platform.paths.get_sub_dir("checkpoints"), "test.lock")
        mgr2 = SingleInstanceManager(self.platform.paths.get_sub_dir("checkpoints"), "test.lock")

        self.assertTrue(mgr1.acquire())
        # Second acquire should fail because lock is held by mgr1
        self.assertFalse(mgr2.acquire())

        mgr1.release()
        # After release, second acquire succeeds
        self.assertTrue(mgr2.acquire())
        mgr2.release()

    def test_08_port_manager_allocation(self):
        """Test dynamic port finding and reservation."""
        ports = self.platform.ports
        free_port = ports.find_available_port(start_port=3050, max_attempts=10)
        self.assertTrue(free_port >= 3050)

        reserved = ports.reserve_port("BackendService", free_port)
        self.assertEqual(ports.get_service_port("BackendService"), reserved)

    def test_09_session_separation(self):
        """Test Session 0 non-interactive service vs interactive user session agent."""
        service = self.platform.service_mgr
        res = service.start_service()
        self.assertTrue(res["session_0_safe"])
        self.assertTrue(res["interactive_ui_disabled"])

        user_agent = self.platform.user_agent
        session_res = user_agent.initialize_session()
        self.assertTrue(session_res["screen_capture_ready"])
        self.assertTrue(session_res["computer_control_ready"])

    def test_10_startup_manager(self):
        """Test enabling and disabling Windows auto-start."""
        startup = self.platform.startup_mgr
        self.assertFalse(startup.is_auto_start_enabled())
        self.assertTrue(startup.enable_auto_start())
        self.assertTrue(startup.is_auto_start_enabled())
        self.assertTrue(startup.disable_auto_start())
        self.assertFalse(startup.is_auto_start_enabled())

    def test_11_crash_manager_secret_redaction(self):
        """Test stack trace secret redaction."""
        crash_mgr = self.platform.crash_mgr
        dirty_stack = "Error at line 42 with token sk-abcdef1234567890abcdef12 and password='SuperSecretPassword'"
        clean = crash_mgr.redact_secrets(dirty_stack)
        self.assertNotIn("sk-abcdef1234567890abcdef12", clean)
        self.assertNotIn("SuperSecretPassword", clean)
        self.assertIn("[REDACTED_SECRET]", clean)

    def test_12_crash_loop_safe_mode(self):
        """Test repeated startup crashes trigger Safe Mode."""
        crash_mgr = self.platform.crash_mgr
        build = BuildInfo(app_version="1.0.0", build_number=100)

        # Crash 1
        r1 = crash_mgr.record_crash("CoreEngine", RuntimeError("First crash"), "stack1", build)
        self.assertFalse(r1.is_safe_mode_triggered)
        self.assertEqual(crash_mgr.get_app_health_state(), AppHealthState.HEALTHY)

        # Crash 2 (rapid)
        r2 = crash_mgr.record_crash("CoreEngine", RuntimeError("Second crash"), "stack2", build)
        self.assertTrue(r2.is_safe_mode_triggered)
        self.assertEqual(crash_mgr.get_app_health_state(), AppHealthState.SAFE_MODE)

        # Reset
        crash_mgr.reset_safe_mode()
        self.assertEqual(crash_mgr.get_app_health_state(), AppHealthState.HEALTHY)

    def test_13_migration_manager_idempotency(self):
        """Test schema migration execution and idempotency."""
        mgr = self.platform.migration_mgr
        res1 = mgr.run_pending_migrations()
        self.assertEqual(res1["status"], "SUCCESS")
        self.assertTrue(res1["executed_count"] >= 2)

        # Running again should execute 0 pending migrations
        res2 = mgr.run_pending_migrations()
        self.assertEqual(res2["status"], "SUCCESS")
        self.assertEqual(res2["executed_count"], 0)

    def test_14_release_channel_isolation(self):
        """Test channel isolation: STABLE rejected BETA update."""
        channel_mgr = self.platform.channel_mgr
        channel_mgr.set_channel(ReleaseChannel.STABLE)

        self.assertTrue(channel_mgr.is_update_eligible(ReleaseChannel.STABLE, ReleaseChannel.STABLE))
        self.assertFalse(channel_mgr.is_update_eligible(ReleaseChannel.STABLE, ReleaseChannel.BETA))
        self.assertFalse(channel_mgr.is_update_eligible(ReleaseChannel.STABLE, ReleaseChannel.DEV))

        # Switch to BETA
        channel_mgr.set_channel(ReleaseChannel.BETA)
        self.assertTrue(channel_mgr.is_update_eligible(ReleaseChannel.BETA, ReleaseChannel.BETA))

    def test_15_code_signing_and_tamper_detection(self):
        """Test cryptographic package checksum and signature verification."""
        signing = self.platform.signing_mgr
        pkg_file = self.platform.paths.get_sub_dir("updates") / "sample_update.bin"
        content = b"CHARLIE_UPDATE_PACKAGE_V1_PAYLOAD"
        pkg_file.write_bytes(content)

        checksum = hashlib.sha256(content).hexdigest()
        manifest = ReleaseManifest(
            version="1.1.0",
            build=110,
            channel=ReleaseChannel.STABLE,
            download_url="https://updates.charlie.local/v1.1.0",
            size_bytes=len(content),
            checksum_sha256=checksum,
            signature="CHARLIE_RELEASE_KEY_V1:sig_token_xyz",
        )

        # Valid package
        ver_res = signing.verify_package(pkg_file, manifest)
        self.assertTrue(ver_res["valid"])

        # Tampered package content
        pkg_file.write_bytes(b"TAMPERED_MALICIOUS_PAYLOAD")
        tamper_res = signing.verify_package(pkg_file, manifest)
        self.assertFalse(tamper_res["valid"])
        self.assertEqual(tamper_res["reason"], "CHECKSUM_MISMATCH")

    def test_16_pre_update_backup_and_auto_rollback(self):
        """Test pre-update backup and automatic rollback on post-update health check failure."""
        update_mgr = self.platform.update_mgr
        content = b"CHARLIE_UPDATE_BIN"
        pkg_file = self.platform.paths.get_sub_dir("updates") / "CHARLIE_Update_1.1.0.bin"
        pkg_file.write_bytes(content)

        manifest = ReleaseManifest(
            version="1.1.0",
            build=110,
            channel=ReleaseChannel.STABLE,
            download_url="https://updates.charlie.local/1.1.0",
            size_bytes=len(content),
            checksum_sha256=hashlib.sha256(content).hexdigest(),
            signature="CHARLIE_RELEASE_KEY_V1:valid",
        )

        # Apply update with a FAILING health check
        def failing_health_check():
            return False

        res = update_mgr.apply_update_with_health_check(
            current_version="1.0.0",
            manifest=manifest,
            staged_package_path=pkg_file,
            health_check_fn=failing_health_check,
        )

        self.assertEqual(res["status"], "ROLLED_BACK")
        self.assertEqual(res["reason"], "POST_UPDATE_HEALTH_CHECK_FAILED")
        self.assertTrue(res["rollback_details"]["success"])
        self.assertEqual(res["rollback_details"]["restored_version"], "1.0.0")

    def test_17_successful_update(self):
        """Test successful update when health check passes."""
        update_mgr = self.platform.update_mgr
        content = b"VALID_UPDATE"
        pkg_file = self.platform.paths.get_sub_dir("updates") / "CHARLIE_Update_1.2.0.bin"
        pkg_file.write_bytes(content)

        manifest = ReleaseManifest(
            version="1.2.0",
            build=120,
            channel=ReleaseChannel.STABLE,
            download_url="https://updates.charlie.local/1.2.0",
            size_bytes=len(content),
            checksum_sha256=hashlib.sha256(content).hexdigest(),
            signature="CHARLIE_RELEASE_KEY_V1:valid",
        )

        res = update_mgr.apply_update_with_health_check(
            current_version="1.0.0",
            manifest=manifest,
            staged_package_path=pkg_file,
            health_check_fn=lambda: True,
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["upgraded_to"], "1.2.0")

    def test_18_uninstaller_user_data_preservation(self):
        """Test uninstaller preserving user data by default, and wiping on full clean."""
        uninstaller = self.platform.uninstall_mgr

        # Write dummy memory file
        mem_file = self.platform.paths.get_sub_dir("memory") / "user_memory.db"
        mem_file.write_text("DUMMY_DATABASE_CONTENT", encoding="utf-8")

        # Standard uninstall: preserve data
        res1 = uninstaller.uninstall(preserve_user_data=True)
        self.assertTrue(res1["success"])
        self.assertTrue(mem_file.exists())

        # Full removal: purge data
        res2 = uninstaller.uninstall(preserve_user_data=False)
        self.assertTrue(res2["success"])
        self.assertFalse(mem_file.exists())

    def test_19_diagnostic_bundle_privacy(self):
        """Test diagnostic export scrubs secrets and includes health states."""
        # Create log file with confidential text
        log_file = self.platform.paths.get_log_file()
        log_file.write_text("INFO: Login token sk-1234567890123456789012 created for user.", encoding="utf-8")

        bundle = self.platform.export_diagnostic_bundle()
        self.assertTrue(bundle.bundle_id.startswith("DIAG_"))
        self.assertEqual(len(bundle.redacted_logs), 1)
        self.assertNotIn("sk-1234567890123456789012", bundle.redacted_logs[0])
        self.assertIn("[REDACTED_SECRET]", bundle.redacted_logs[0])

    def test_20_inno_setup_builder(self):
        """Test generating Inno Setup script."""
        builder = self.platform.installer_builder
        script = builder.generate_inno_setup_script(app_name="CHARLIE", version="1.0.0", install_mode=InstallMode.PER_USER)
        self.assertIn("AppName=CHARLIE", script)
        self.assertIn("PrivilegesRequired=lowest", script)
        self.assertIn("CHARLIE-Setup", script)

    def test_21_deployment_control_actions(self):
        """Test assistant deployment action tool."""
        actions = DeploymentControlActions(self.platform)
        status = actions.get_deployment_status()
        self.assertEqual(status["health_state"], "HEALTHY")

        env = actions.check_environment()
        self.assertTrue("Windows" in env["os"] or env["is_supported"])

        diag = actions.export_diagnostics()
        self.assertTrue(diag["bundle_id"].startswith("DIAG_"))

        safe = actions.toggle_safe_mode(True)
        self.assertEqual(safe["health_state"], "SAFE_MODE")
        safe_off = actions.toggle_safe_mode(False)
        self.assertEqual(safe_off["health_state"], "HEALTHY")


if __name__ == "__main__":
    unittest.main()
