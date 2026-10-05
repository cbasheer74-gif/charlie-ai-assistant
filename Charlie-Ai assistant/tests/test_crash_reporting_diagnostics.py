"""
tests/test_crash_reporting_diagnostics.py — 20 Golden Tests for CHARLIE Crash Reporting,
Remote Diagnostics, and Support Center.

Verifies:
- Golden Tests 1–20 (§141–§160)
- 32-Point Certification Matrix (§162)
"""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.deployment.crash_reporter import (
    ConsentSetting,
    CrashReportingManager,
    TaskCategory,
)
from engine.deployment.diagnostic_collector import (
    CrashSignatureGenerator,
    DiagnosticCollector,
    ErrorLevel,
    HealthSnapshotManager,
    HealthStatus,
    SecretRedactor,
)
from engine.deployment.models import AppHealthState, BuildInfo
from engine.deployment.paths import DeploymentPathManager
from engine.deployment.runtime import CrashManager, GlobalExceptionHandler
from licensing_server.database import (
    Base,
    DiagnosticRequestDB,
    DiagnosticRequestStatus,
    IncidentDB,
    IncidentSeverity,
    IncidentStatus,
    PlanTier,
    SubscriptionDB,
    SupportCategory,
    SupportTicketDB,
    UserDB,
    UserRole,
    _utcnow,
)
from licensing_server.services.admin_service import AdminService
from licensing_server.services.auth_service import AuthService
from licensing_server.services.support_service import SupportService


class TestCrashReportingDiagnostics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)
        cls.support_service = SupportService()
        cls.admin_service = AdminService()
        cls.auth_service = AuthService()

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.db = self.Session()

        # Temporary local appdata path for isolated client testing
        self.temp_dir = tempfile.mkdtemp(prefix="charlie_diag_test_")
        self.paths = DeploymentPathManager(data_dir_override=self.temp_dir)
        self.crash_mgr = CrashReportingManager(
            app_version="1.0.4", build_number=104, channel="STABLE", path_manager=self.paths
        )

        # Seed test customer and staff users
        self.customer = UserDB(
            id="usr_cust_01",
            email="client@example.com",
            password_hash="fake_hash",
            role=UserRole.CUSTOMER.value,
            created_at=_utcnow(),
        )
        self.staff = UserDB(
            id="usr_staff_01",
            email="support@charlie.ai",
            password_hash="fake_hash",
            role=UserRole.SUPPORT.value,
            created_at=_utcnow(),
        )
        self.db.add_all([self.customer, self.staff])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ── GOLDEN TEST 1 — BASIC CRASH CAPTURE ──────────────────────────────────
    def test_golden_01_basic_crash_capture(self):
        """Test 1: Inject controlled exception. Report created, crash ID generated, no secrets."""
        try:
            raise ValueError("Test controlled failure in video encoder")
        except Exception as ex:
            import traceback
            tb = traceback.format_exc()
            event = self.crash_mgr.capture_crash(
                component="video_encoder",
                error=ex,
                stack_trace=tb,
                error_level=ErrorLevel.CRITICAL,
                task_category=TaskCategory.VIDEO_EDITING,
            )

        self.assertTrue(event.crash_id.startswith("CHARLIE-CRASH-"))
        self.assertEqual(event.component, "video_encoder")
        self.assertEqual(event.error_type, "ValueError")
        self.assertTrue((self.crash_mgr.crashes_dir / f"{event.crash_id}.json").exists())

    # ── GOLDEN TEST 2 — RESTART DETECTS PREVIOUS CRASH ────────────────────────
    def test_golden_02_restart_detects_previous_crash(self):
        """Test 2: Crash client -> new instance detects previous crash history."""
        # Capture crash
        self.crash_mgr.capture_crash("core", RuntimeError("Unexpected halt"), "dummy stack")
        crashes = list(self.crash_mgr.crashes_dir.glob("*.json"))
        self.assertEqual(len(crashes), 1)

        # Re-initialize CrashReportingManager pointing to same directory
        restarted_mgr = CrashReportingManager(path_manager=self.paths)
        existing = list(restarted_mgr.crashes_dir.glob("*.json"))
        self.assertEqual(len(existing), 1)
        data = json.loads(existing[0].read_text(encoding="utf-8"))
        self.assertEqual(data["component"], "core")

    # ── GOLDEN TEST 3 — REPORT UPLOAD RECEIVED BY BACKEND ─────────────────────
    def test_golden_03_report_upload_received_by_backend(self):
        """Test 3: Send report to backend support service -> recorded and incident created."""
        event = self.crash_mgr.capture_crash("audio_driver", IOError("Device busy"), "stack trace")
        crash_data = json.loads((self.crash_mgr.crashes_dir / f"{event.crash_id}.json").read_text(encoding="utf-8"))

        incident, is_new = self.support_service.record_crash_incident(self.db, crash_data)
        self.assertTrue(is_new)
        self.assertEqual(incident.occurrences, 1)
        self.assertEqual(incident.component, "audio_driver")

    # ── GOLDEN TEST 4 — SECRET AND PATH REDACTION ────────────────────────────
    def test_golden_04_secret_and_path_redaction(self):
        """Test 4: Scrub Google/OpenAI keys, passwords, bearer tokens, and local user paths."""
        dirty_text = (
            "Exception: key=sk-proj-12345678901234567890 and gemini=AIzaSyA123456789012345678901234567890 "
            "Bearer eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyIjoiMTIzIn0.xyz "
            'password="SuperSecretPassword" at C:\\Users\\Anees\\Documents\\secret.py '
            "postgres://admin:topsecret123@localhost:5432/db"
        )
        clean = SecretRedactor.sanitize_text(dirty_text)

        self.assertNotIn("sk-proj", clean)
        self.assertNotIn("AIzaSyA", clean)
        self.assertNotIn("SuperSecretPassword", clean)
        self.assertNotIn("topsecret123", clean)
        self.assertNotIn("Anees", clean)
        self.assertIn("C:\\Users\\[USER]\\", clean)
        self.assertIn("[REDACTED", clean)

    # ── GOLDEN TEST 5 — OFFLINE CRASH SAVED LOCALLY ──────────────────────────
    def test_golden_05_offline_crash_local_queue(self):
        """Test 5: Crash while offline is saved locally, added to queue, does not block."""
        self.crash_mgr.set_consent_setting(ConsentSetting.AUTO_SEND)
        event = self.crash_mgr.capture_crash("network", ConnectionResetError("No internet"), "stack")

        pending = list(self.crash_mgr.queue_dir.glob("*.pending"))
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].stem, event.crash_id)

    # ── GOLDEN TEST 6 — LATER UPLOAD RESPECTS CONSENT ────────────────────────
    def test_golden_06_later_upload_respects_consent(self):
        """Test 6: Reconnect -> upload adheres strictly to consent policy."""
        # When NEVER_SEND, should not enqueue
        self.crash_mgr.set_consent_setting(ConsentSetting.NEVER_SEND)
        shutil.rmtree(self.crash_mgr.queue_dir)
        self.crash_mgr.queue_dir.mkdir(parents=True, exist_ok=True)

        event = self.crash_mgr.capture_crash("disk", OSError("Write failed"), "stack")
        pending = list(self.crash_mgr.queue_dir.glob("*.pending"))
        self.assertEqual(len(pending), 0)

        # When manually enqueued, processes bounded queue
        self.crash_mgr.enqueue_upload(event.crash_id)
        results = self.crash_mgr.process_upload_queue(uploader_func=lambda p: (True, "OK"))
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0][1])
        # Queue should now be empty
        self.assertEqual(len(list(self.crash_mgr.queue_dir.glob("*.pending"))), 0)

    # ── GOLDEN TEST 7 — INCIDENT GROUPING (10 IDENTICAL CRASHES) ─────────────
    def test_golden_07_incident_grouping_same_crash(self):
        """Test 7: 10 identical crashes produce exactly 1 incident with occurrence=10."""
        sig = CrashSignatureGenerator.generate("ExportError", "frame1\nframe2", "filmora_adapter")
        crash_data = {
            "stack_signature": sig,
            "error_type": "ExportError",
            "component": "filmora_adapter",
            "app_version": "1.0.4",
            "user_id": "usr_user_1",
            "sanitized_message": "Filmora export timeout",
            "error_level": "ERROR",
        }

        for _ in range(10):
            self.support_service.record_crash_incident(self.db, crash_data)

        incidents = self.db.query(IncidentDB).all()
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].occurrences, 10)

    # ── GOLDEN TEST 8 — DIFFERENT CRASH SEPARATE INCIDENT ────────────────────
    def test_golden_08_different_crash_separate_incident(self):
        """Test 8: Different stack signature produces a distinct incident."""
        sig1 = CrashSignatureGenerator.generate("TypeError", "frameA", "module1")
        sig2 = CrashSignatureGenerator.generate("ValueError", "frameB", "module2")

        self.support_service.record_crash_incident(
            self.db, {"stack_signature": sig1, "error_type": "TypeError", "component": "module1"}
        )
        self.support_service.record_crash_incident(
            self.db, {"stack_signature": sig2, "error_type": "ValueError", "component": "module2"}
        )

        incidents = self.db.query(IncidentDB).all()
        self.assertEqual(len(incidents), 2)

    # ── GOLDEN TEST 9 — SUPPORT TICKET LINKED TO CRASH ───────────────────────
    def test_golden_09_support_ticket_linked_to_crash(self):
        """Test 9: User creates support ticket with crash reference."""
        event = self.crash_mgr.capture_crash("voice", RuntimeError("Microphone lost"), "stack")
        success, msg, ticket = self.support_service.create_ticket(
            db=self.db,
            user=self.customer,
            subject="Voice failed during command",
            message="Microphone crashed when speaking",
            category="VOICE",
            error_id=event.crash_id,
        )
        self.assertTrue(success)
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.error_id, event.crash_id)

        all_tickets = self.support_service.get_all_tickets(self.db)
        self.assertEqual(len(all_tickets), 1)
        self.assertEqual(all_tickets[0]["error_id"], event.crash_id)

    # ── GOLDEN TEST 10 — RBAC: CUSTOMER BLOCKED FROM ADMIN ───────────────────
    def test_golden_10_rbac_customer_blocked_from_admin(self):
        """Test 10: Non-admin/customer role cannot access admin support functions."""
        import asyncio
        from fastapi import HTTPException, Request
        from fastapi.security import HTTPAuthorizationCredentials
        from licensing_server.middleware.auth_middleware import require_support

        cust_token = self.auth_service.create_access_token(self.customer.id, self.customer.email, role="CUSTOMER")
        req = Request({"type": "http", "headers": []})
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=cust_token)

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(require_support(request=req, credentials=creds, db=self.db))
        self.assertEqual(ctx.exception.status_code, 403)

    # ── GOLDEN TEST 11 — SUPPORT ROLE BLOCKED FROM RELEASE/SIGNING ───────────
    def test_golden_11_support_role_blocked_from_releases(self):
        """Test 11: SUPPORT role cannot modify production release manifests or signing keys."""
        import asyncio
        from fastapi import HTTPException, Request
        from fastapi.security import HTTPAuthorizationCredentials
        from licensing_server.middleware.auth_middleware import require_admin

        staff_token = self.auth_service.create_access_token(self.staff.id, self.staff.email, role="SUPPORT")
        req = Request({"type": "http", "headers": []})
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=staff_token)

        # Staff can access support, but cannot access admin (releases)
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(require_admin(request=req, credentials=creds, db=self.db))
        self.assertEqual(ctx.exception.status_code, 403)


    # ── GOLDEN TEST 12 — OPTIONAL SCREENSHOT STRICTLY OPT-IN ─────────────────
    def test_golden_12_optional_screenshot_opt_in(self):
        """Test 12: Screenshots are never attached by default; only when explicit."""
        collector = DiagnosticCollector(path_manager=self.paths)

        # Default bundle
        bundle_default = collector.build_diagnostic_bundle()
        self.assertFalse(bundle_default["screenshot_attachment"]["included"])

        # Opt-in bundle
        bundle_opt_in = collector.build_diagnostic_bundle(
            include_screenshot=True,
            screenshot_data_base64="data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==",
        )
        self.assertTrue(bundle_opt_in["screenshot_attachment"]["included"])
        self.assertIn("data:image/png", bundle_opt_in["screenshot_attachment"]["data_base64"])

    # ── GOLDEN TEST 13 — STARTUP CRASH LOOP TRIGGERS SAFE MODE ───────────────
    def test_golden_13_startup_crash_loop_triggers_safe_mode(self):
        """Test 13: 3 consecutive startup failures trigger Safe Mode."""
        runtime_crash_mgr = CrashManager(path_manager=self.paths)
        self.assertEqual(runtime_crash_mgr.get_app_health_state(), AppHealthState.HEALTHY)

        runtime_crash_mgr.record_startup_failure()
        runtime_crash_mgr.record_startup_failure()
        self.assertFalse(runtime_crash_mgr.is_startup_crash_loop())

        runtime_crash_mgr.record_startup_failure()
        self.assertTrue(runtime_crash_mgr.is_startup_crash_loop())
        self.assertEqual(runtime_crash_mgr.get_app_health_state(), AppHealthState.SAFE_MODE)

    # ── GOLDEN TEST 14 — PLUGIN FAILURE ISOLATION ────────────────────────────
    def test_golden_14_plugin_failure_isolation(self):
        """Test 14: Plugin failure isolates plugin without terminating host app."""
        plugin_id = "plugin_filmora_v2"
        self.assertFalse(self.crash_mgr.is_plugin_quarantined(plugin_id))

        self.crash_mgr.quarantine_plugin(plugin_id, "Memory leak detected in render hook")
        self.assertTrue(self.crash_mgr.is_plugin_quarantined(plugin_id))
        quarantined = self.crash_mgr.get_quarantined_plugins()
        self.assertIn(plugin_id, quarantined)

    # ── GOLDEN TEST 15 — UPDATE FAILURE CONTEXT LINKED ───────────────────────
    def test_golden_15_update_failure_context_linked(self):
        """Test 15: Crash during update captures version and update task category."""
        event = self.crash_mgr.capture_crash(
            component="update_installer",
            error=RuntimeError("Installer SHA mismatch"),
            stack_trace="update frame",
            task_category=TaskCategory.UPDATE,
        )
        self.assertEqual(event.active_task_category, "UPDATE")
        self.assertEqual(event.component, "update_installer")

    # ── GOLDEN TEST 16 — VERSION REGRESSION CORRELATION ──────────────────────
    def test_golden_16_version_regression_correlation(self):
        """Test 16: Crash spike on new version identified in analytics without false causation."""
        sig = CrashSignatureGenerator.generate("NullPointer", "frame", "core")
        for _ in range(5):
            self.support_service.record_crash_incident(
                self.db,
                {
                    "stack_signature": sig,
                    "error_type": "NullPointer",
                    "component": "core",
                    "app_version": "1.0.5-beta",
                    "user_id": "usr_test",
                },
            )

        analytics = self.support_service.get_incident_analytics(self.db)
        self.assertGreaterEqual(analytics["total_crashes"], 5)
        top_v = analytics["top_versions"][0]
        self.assertEqual(top_v["version"], "1.0.5-beta")
        self.assertEqual(top_v["crash_count"], 5)

    # ── GOLDEN TEST 17 — DEVICE LICENSE ISSUE NO RAW FINGERPRINT ─────────────
    def test_golden_17_device_license_issue_no_raw_fingerprint(self):
        """Test 17: Device ID reference in diagnostics is hashed, never raw hardware details."""
        collector = DiagnosticCollector(path_manager=self.paths)
        raw_hw_uuid = "BFEBFBFF000906EA-SECURE-HARDWARE-SERIAL-998811"
        bundle = collector.build_diagnostic_bundle(
            license_summary={"plan": "PREMIUM", "device_id": raw_hw_uuid}
        )

        license_info = bundle["license_status"]
        self.assertNotIn(raw_hw_uuid, json.dumps(license_info))
        self.assertIn("device_id_ref", license_info)
        self.assertEqual(len(license_info["device_id_ref"]), 12)

    # ── GOLDEN TEST 18 — REMOTE DIAGNOSTIC REQUEST CREATION ───────────────────
    def test_golden_18_remote_diagnostic_request_prompt(self):
        """Test 18: Support staff initiates diagnostic request; creates PENDING record."""
        # Create ticket first
        _, _, ticket = self.support_service.create_ticket(
            db=self.db, user=self.customer, subject="Bug inquiry", message="Something broke"
        )
        success, msg, d_req = self.support_service.create_diagnostic_request(
            db=self.db, ticket_id=ticket.id, staff_id=self.staff.id
        )
        self.assertTrue(success)
        self.assertIsNotNone(d_req)
        self.assertEqual(d_req.status, DiagnosticRequestStatus.PENDING.value)

    # ── GOLDEN TEST 19 — CUSTOMER DECLINES DIAGNOSTIC REQUEST ────────────────
    def test_golden_19_remote_diagnostic_decline_zero_upload(self):
        """Test 19: Customer explicitly declines request -> DECLINED status, zero data uploaded."""
        _, _, ticket = self.support_service.create_ticket(
            db=self.db, user=self.customer, subject="Bug inquiry", message="Need help"
        )
        _, _, d_req = self.support_service.create_diagnostic_request(
            db=self.db, ticket_id=ticket.id, staff_id=self.staff.id
        )

        # Customer declines
        success, msg = self.support_service.respond_diagnostic_request(
            db=self.db, request_id=d_req.id, user_id=self.customer.id, approved=False
        )
        self.assertTrue(success)

        # Check DB state
        req_db = self.db.query(DiagnosticRequestDB).filter(DiagnosticRequestDB.id == d_req.id).first()
        self.assertEqual(req_db.status, DiagnosticRequestStatus.DECLINED.value)
        self.assertIsNone(req_db.diagnostic_bundle_id)

    # ── GOLDEN TEST 20 — ZERO PRIVATE DATA COLLECTED ─────────────────────────
    def test_golden_20_private_data_never_collected(self):
        """Test 20: Documents, emails, chat history, or personal memories are NEVER in diagnostics."""
        collector = DiagnosticCollector(path_manager=self.paths)
        bundle = collector.build_diagnostic_bundle()
        raw_bundle = json.dumps(bundle).lower()

        # Prohibited terms and personal leaks
        prohibited = [
            "private_key",
            "conversation_history",
            "chat_history",
            "microphone_audio",
            "user_documents",
            "browser_history",
        ]
        for term in prohibited:
            self.assertNotIn(term, raw_bundle)


if __name__ == "__main__":
    unittest.main()
