"""
CHARLIE Phase 10: Multi-Device Test Suite
Validates Golden Tests 102-120 and Section 121 Certification Matrix:
- Pairing & QR generation
- Mutual Authentication & Cryptographic Identity
- Replay & Nonce protection
- Expired command TTL purge
- Safe remote commands vs Raw shell blocking
- Voice intent routing
- High impact actions & confirmation binding
- Device revocation & lost device workflow
- Offline queueing & status
- Selective memory sync & sensitive key blocking
- Conflict resolution
- Task handoff & continuity
- Secure file transfer with hash validation
- Notification privacy masking & deduplication
- Protocol version compatibility
"""

import os
import shutil
import tempfile
import time
import unittest
import uuid

from engine.devices.core import DeviceOrchestrator
from engine.devices.models import (
    DeviceIdentity,
    DeviceType,
    NotificationCategory,
    RemoteCommandEnvelope,
    RemotePermission,
    SyncScope,
    TrustState,
)


class TestPhase10MultiDevice(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_devices.db")
        self.orchestrator = DeviceOrchestrator(db_path=self.db_path)

        # Helper to pair a test mobile device
        self.session_id, self.pairing_code, self.qr = self.orchestrator.pairing_manager.create_pairing_session()
        self.client_device_id = "phone_pixel_8"
        ok, msg, self.device = self.orchestrator.pairing_manager.complete_pairing(
            session_id=self.session_id,
            provided_code=self.pairing_code,
            client_device_id=self.client_device_id,
            client_device_name="Aney's Pixel 8",
            client_device_type=DeviceType.ANDROID,
            client_public_key="pubkey_android_mock_12345",
        )
        self.assertTrue(ok, f"Setup pairing failed: {msg}")

        # Create active session
        self.session = self.orchestrator.session_manager.create_session(self.client_device_id)
        self.assertIsNotNone(self.session)

    def tearDown(self):
        try:
            shutil.rmtree(self.test_dir)
        except Exception:
            pass

    # --- 102. Golden Test: Pairing ---
    def test_golden_102_secure_pairing(self):
        s_id, code, qr = self.orchestrator.pairing_manager.create_pairing_session()
        self.assertIn("pairing_session_id", qr)
        self.assertIn("ephemeral_public_key", qr)

        # Pair second device
        ok, msg, dev = self.orchestrator.pairing_manager.complete_pairing(
            session_id=s_id,
            provided_code=code,
            client_device_id="iphone_15",
            client_device_name="Aney's iPhone",
            client_device_type=DeviceType.IOS,
            client_public_key="pubkey_ios_mock_98765",
        )
        self.assertTrue(ok)
        self.assertEqual(dev.trust_state, TrustState.TRUSTED)

        # Verify pairing code cannot be reused (consumed)
        ok_reuse, _, _ = self.orchestrator.pairing_manager.complete_pairing(
            session_id=s_id,
            provided_code=code,
            client_device_id="rogue_phone",
            client_device_name="Rogue Phone",
            client_device_type=DeviceType.ANDROID,
            client_public_key="pubkey_rogue",
        )
        self.assertFalse(ok_reuse)

    # --- 103. Golden Test: Replay Attack ---
    def test_golden_103_replay_attack_prevention(self):
        env = RemoteCommandEnvelope(
            command_id=f"cmd_{uuid.uuid4().hex[:8]}",
            device_id=self.client_device_id,
            session_id=self.session.session_id,
            intent="GET_STATUS",
            nonce="nonce_unique_103",
            timestamp=time.time(),
        )

        res1 = self.orchestrator.handle_remote_envelope(env)
        self.assertTrue(res1["success"])

        # Replay the same envelope with same nonce & command_id
        res2 = self.orchestrator.handle_remote_envelope(env)
        self.assertFalse(res2["success"])
        self.assertIn("Replay attack detected", res2["error"])

    # --- 104. Golden Test: Expired Command TTL ---
    def test_golden_104_expired_command_ttl(self):
        env = RemoteCommandEnvelope(
            command_id="cmd_stale_104",
            device_id=self.client_device_id,
            session_id=self.session.session_id,
            intent="OPEN_APP",
            parameters={"app_name": "Chrome"},
            timestamp=time.time() - 400.0,
            ttl_seconds=300.0,  # 5 min TTL, but 400s elapsed
        )

        res = self.orchestrator.handle_remote_envelope(env)
        self.assertFalse(res["success"])
        self.assertIn("expired", res["error"].lower())

    # --- 105. Golden Test: Safe Remote Command ---
    def test_golden_105_safe_remote_command(self):
        env = RemoteCommandEnvelope(
            command_id="cmd_safe_105",
            device_id=self.client_device_id,
            session_id=self.session.session_id,
            intent="OPEN_APP",
            parameters={"app_name": "Notepad"},
            timestamp=time.time(),
        )

        res = self.orchestrator.handle_remote_envelope(env)
        self.assertTrue(res["success"])
        self.assertEqual(res["result"]["status"], "LAUNCHED")
        self.assertTrue(res["result"]["verified"])

    # --- 106. Golden Test: Raw Shell Attempt Blocked ---
    def test_golden_106_raw_shell_attempt_blocked(self):
        # 1. Direct raw shell key attempt
        env = RemoteCommandEnvelope(
            command_id="cmd_raw_106_1",
            device_id=self.client_device_id,
            session_id=self.session.session_id,
            intent="START_PROJECT",
            timestamp=time.time(),
        )
        raw_payload = {"command": "powershell.exe -Command Get-Process"}
        res1 = self.orchestrator.handle_remote_envelope(env, raw_dict=raw_payload)
        self.assertFalse(res1["success"])
        self.assertEqual(res1["details"]["error"], "RAW_SHELL_FORBIDDEN")

        # 2. Dangerous script in parameters
        env2 = RemoteCommandEnvelope(
            command_id="cmd_raw_106_2",
            device_id=self.client_device_id,
            session_id=self.session.session_id,
            intent="START_PROJECT",
            parameters={"script": "powershell.exe Remove-Item C:\\Windows"},
            timestamp=time.time(),
        )
        res2 = self.orchestrator.handle_remote_envelope(env2)
        self.assertFalse(res2["success"])
        self.assertEqual(res2["details"]["error"], "DANGEROUS_SCRIPT_BLOCKED")

    # --- 107. Golden Test: Project Status ---
    def test_golden_107_project_status(self):
        env = RemoteCommandEnvelope(
            command_id="cmd_project_107",
            device_id=self.client_device_id,
            session_id=self.session.session_id,
            intent="GET_PROJECT_STATUS",
            parameters={"project_name": "ZynPay"},
            timestamp=time.time(),
        )

        res = self.orchestrator.handle_remote_envelope(env)
        self.assertTrue(res["success"])
        self.assertEqual(res["result"]["project_name"], "ZynPay")
        self.assertEqual(res["result"]["port"], 8080)
        self.assertTrue(res["result"]["tests_passing"])

    # --- 108. Golden Test: Voice Intent ---
    def test_golden_108_mobile_voice_intent(self):
        # Mobile STT converts voice "Charlie continue last project" into START_PROJECT intent
        env = RemoteCommandEnvelope(
            command_id="cmd_voice_108",
            device_id=self.client_device_id,
            session_id=self.session.session_id,
            intent="START_PROJECT",
            parameters={"project_name": "ZynPay"},
            timestamp=time.time(),
        )

        res = self.orchestrator.handle_remote_envelope(env)
        self.assertTrue(res["success"])
        self.assertEqual(res["result"]["status"], "STARTED")
        self.assertEqual(res["result"]["verified_port"], 8080)

    # --- 109. Golden Test: High Impact Confirmation ---
    def test_golden_109_high_impact_shutdown_confirmation(self):
        env = RemoteCommandEnvelope(
            command_id="cmd_shutdown_109",
            device_id=self.client_device_id,
            session_id=self.session.session_id,
            intent="PC_SHUTDOWN",
            timestamp=time.time(),
        )

        res = self.orchestrator.handle_remote_envelope(env)
        self.assertTrue(res["success"])
        # Must require confirmation, not shut down immediately
        self.assertTrue(res["result"]["requires_confirmation"])
        self.assertEqual(res["result"]["status"], "CONFIRMATION_PENDING")

    # --- 110. Golden Test: Revoked Phone ---
    def test_golden_110_revoked_phone_blocked(self):
        # Revoke device
        self.orchestrator.revocation_manager.revoke_device(self.client_device_id)

        env = RemoteCommandEnvelope(
            command_id="cmd_revoked_110",
            device_id=self.client_device_id,
            session_id=self.session.session_id,
            intent="GET_STATUS",
            timestamp=time.time(),
        )

        res = self.orchestrator.handle_remote_envelope(env)
        self.assertFalse(res["success"])
        self.assertEqual(res["details"]["error"], "DEVICE_REVOKED")

    # --- 111. Golden Test: Lost Device Workflow ---
    def test_golden_111_lost_device_session_invalidation(self):
        # Verify active session exists
        valid_before, _ = self.orchestrator.session_manager.validate_session(self.session.session_id)
        self.assertTrue(valid_before)

        # Trigger desktop revocation (Lost Phone Mode)
        self.orchestrator.revocation_manager.revoke_device(self.client_device_id, reason="Lost phone reported")

        # Verify session is immediately destroyed
        valid_after, _ = self.orchestrator.session_manager.validate_session(self.session.session_id)
        self.assertFalse(valid_after)

    # --- 112. Golden Test: Offline PC & Queueing ---
    def test_golden_112_offline_pc_queueing(self):
        from engine.devices.models import PresenceStatus
        self.orchestrator.presence_manager.set_pc_status(PresenceStatus.OFFLINE)

        # Safe task should be queued
        env_safe = RemoteCommandEnvelope(
            command_id="cmd_queue_safe_112",
            device_id=self.client_device_id,
            session_id=self.session.session_id,
            intent="GET_PROJECT_STATUS",
            parameters={"project_name": "ZynPay"},
            timestamp=time.time(),
        )
        res_safe = self.orchestrator.handle_remote_envelope(env_safe)
        self.assertTrue(res_safe["success"])
        self.assertEqual(res_safe["status"], "QUEUED_OFFLINE")
        self.assertEqual(self.orchestrator.offline_queue.get_queued_count(), 1)

        # High risk action must NOT be queued offline
        env_dangerous = RemoteCommandEnvelope(
            command_id="cmd_queue_dangerous_112",
            device_id=self.client_device_id,
            session_id=self.session.session_id,
            intent="PC_SHUTDOWN",
            timestamp=time.time(),
        )
        res_dangerous = self.orchestrator.handle_remote_envelope(env_dangerous)
        self.assertFalse(res_dangerous["success"])
        self.assertIn("cannot be queued offline", res_dangerous["message"])

        # Drain when PC returns online
        self.orchestrator.presence_manager.set_pc_status(PresenceStatus.ONLINE)
        executable = self.orchestrator.offline_queue.drain_executable_commands()
        self.assertEqual(len(executable), 1)
        self.assertEqual(executable[0].command_id, "cmd_queue_safe_112")

    # --- 113. Golden Test: Selective Sync ---
    def test_golden_113_selective_memory_sync(self):
        # 1. Safe settings sync
        ok, msg, record = self.orchestrator.sync_engine.prepare_sync_record(
            record_id="pref_theme",
            scope=SyncScope.SETTINGS,
            data={"theme": "dark", "video_duration": 30},
            origin_device=self.client_device_id,
            version=1,
        )
        self.assertTrue(ok)
        self.assertIsNotNone(record)
        apply_ok, _ = self.orchestrator.sync_engine.apply_remote_record(record)
        self.assertTrue(apply_ok)

        # 2. Sensitive secret sync attempt MUST BE REFUSED
        ok_secret, msg_secret, _ = self.orchestrator.sync_engine.prepare_sync_record(
            record_id="leak_attempt",
            scope=SyncScope.SETTINGS,
            data={"api_key": "sk-1234567890", "oauth_token": "bearer-xyz"},
            origin_device=self.client_device_id,
            version=1,
        )
        self.assertFalse(ok_secret)
        self.assertIn("Prohibited sensitive key", msg_secret)

    # --- 114. Golden Test: Conflict Resolution ---
    def test_golden_114_sync_conflict_resolution(self):
        from engine.devices.models import SyncRecord
        local_rec = SyncRecord(
            record_id="pref_video_dur",
            scope=SyncScope.SETTINGS,
            version=1,
            data={"duration": 45},
            origin_device="host_windows_pc",
            updated_at=time.time() - 10.0,
            data_hash="hash_local",
        )
        remote_rec = SyncRecord(
            record_id="pref_video_dur",
            scope=SyncScope.SETTINGS,
            version=1,
            data={"duration": 30},
            origin_device="phone_pixel_8",
            updated_at=time.time(),
            data_hash="hash_remote",
        )

        is_conflict = self.orchestrator.conflict_resolver.detect_conflict(local_rec, remote_rec)
        self.assertTrue(is_conflict)

        # Resolve via latest verified
        resolved, desc = self.orchestrator.conflict_resolver.resolve(local_rec, remote_rec, strategy="LATEST_VERIFIED")
        self.assertEqual(resolved.data["duration"], 30)
        self.assertGreater(resolved.version, 1)

    # --- 115. Golden Test: Secure File Transfer ---
    def test_golden_115_secure_file_transfer(self):
        sample_report = b"Report: ZynPay financial summary verified."
        ok, msg, token = self.orchestrator.file_transfer.generate_download_token(
            file_path="C:/reports/zynpay_summary.txt",
            project_id="ZynPay",
            target_device_id=self.client_device_id,
            file_content=sample_report,
            file_name="zynpay_summary.txt",
        )
        self.assertTrue(ok)
        self.assertIsNotNone(token)

        # Mobile claims file
        claim_ok, claim_msg, content, file_hash = self.orchestrator.file_transfer.claim_file(
            token=token, requesting_device_id=self.client_device_id
        )
        self.assertTrue(claim_ok)
        self.assertEqual(content, sample_report)

        # Reusing token must fail (one-time use)
        claim_again, _, _, _ = self.orchestrator.file_transfer.claim_file(token, self.client_device_id)
        self.assertFalse(claim_again)

    # --- 116. Golden Test: Wrong File / Scoping ---
    def test_golden_116_wrong_file_recipient(self):
        sample_report = b"Confidential system log"
        ok, _, token = self.orchestrator.file_transfer.generate_download_token(
            file_path="C:/logs/secret.log",
            project_id="System",
            target_device_id="authorized_tablet",
            file_content=sample_report,
            file_name="secret.log",
        )
        self.assertTrue(ok)

        # Pixel 8 attempts to download tablet's file
        claim_ok, msg, _, _ = self.orchestrator.file_transfer.claim_file(token, self.client_device_id)
        self.assertFalse(claim_ok)
        self.assertIn("does not match authorized recipient", msg)

    # --- 117. Golden Test: Mobile Confirmation Binding ---
    def test_golden_117_mobile_confirmation_binding(self):
        ok, msg, notif = self.orchestrator.notifications.dispatch_notification(
            category=NotificationCategory.CONFIRMATION_REQUIRED,
            title="Send Client Email",
            summary="Confirmation needed to send ZynPay audit email to client@bank.com",
            requires_approval=True,
            approval_action_payload={"action": "SEND_EMAIL", "to": "client@bank.com", "subject": "Audit Complete"},
            target_device_id=self.client_device_id,
        )
        self.assertTrue(ok)
        self.assertIsNotNone(notif.action_token)

        # User confirms from mobile
        appr_ok, appr_msg, payload = self.orchestrator.notifications.process_confirmation(
            action_token=notif.action_token, approved=True
        )
        self.assertTrue(appr_ok)
        self.assertEqual(payload["to"], "client@bank.com")

        # Second attempt to use the same token must fail (replay prevention)
        appr_again, _, _ = self.orchestrator.notifications.process_confirmation(notif.action_token, True)
        self.assertFalse(appr_again)

    # --- 118. Golden Test: Notification Privacy Masking ---
    def test_golden_118_notification_privacy_masking(self):
        ok, _, notif = self.orchestrator.notifications.dispatch_notification(
            category=NotificationCategory.TASK_FAILED,
            title="Banking Ledger Failure",
            summary="Client bank statement processing failed for account #998822",
            details={"account_number": "998822", "balance": 150000},
            privacy_safe_text="CHARLIE: Task encountered an issue.",
            target_device_id=self.client_device_id,
        )
        self.assertTrue(ok)
        # Lock screen text must be masked
        self.assertEqual(notif.privacy_safe_text, "CHARLIE: Task encountered an issue.")
        self.assertNotIn("998822", notif.privacy_safe_text)

    # --- 119. Golden Test: Task Handoff ---
    def test_golden_119_task_handoff(self):
        handoff = self.orchestrator.handoff_manager.prepare_handoff(
            task_id="task_research_01",
            source_device=self.client_device_id,
            target_device="host_windows_pc",
            goal="Research microservices caching",
            state_snapshot={"step": 3, "findings": ["Redis cluster recommended"]},
        )
        self.assertIsNotNone(handoff.handoff_id)

        # Claim on Windows host
        claimed = self.orchestrator.handoff_manager.claim_handoff(
            handoff_id=handoff.handoff_id, claiming_device_id="host_windows_pc"
        )
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.goal, "Research microservices caching")
        self.assertIn("findings", claimed.state_snapshot)

    # --- 120. Golden Test: Version Mismatch ---
    def test_golden_120_version_mismatch(self):
        env = RemoteCommandEnvelope(
            command_id="cmd_ver_120",
            protocol_version="v0.2_deprecated",
            device_id=self.client_device_id,
            session_id=self.session.session_id,
            intent="GET_STATUS",
            timestamp=time.time(),
        )

        res = self.orchestrator.handle_remote_envelope(env)
        self.assertFalse(res["success"])
        self.assertEqual(res["details"]["error"], "PROTOCOL_MISMATCH")


if __name__ == "__main__":
    unittest.main()
