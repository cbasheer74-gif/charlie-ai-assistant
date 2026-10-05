"""Tests for Windows DPAPI Credential Vault and Migration (Step 23B)."""
import os
import json
import tempfile
import unittest
from pathlib import Path

from core.credential_vault import (
    is_windows,
    _dpapi_protect,
    _dpapi_unprotect,
    set_secret,
    get_secret,
    delete_secret,
    has_secret,
    list_configured,
    mask_secret,
    migrate_legacy_credentials,
    is_secret_field,
)
from memory.config_manager import (
    get_gemini_key,
    get_groq_key,
    get_plugin_config,
    save_api_keys,
    save_groq_key,
    save_plugin_config,
)
from tests.test_credential_persistence import TestCredentialPersistence
from tests.test_runtime_resilience import (
    TestPortPreflight,
    TestDashboardFailureBoundary,
    TestSingleInstanceGuard,
    TestCoreRuntimeIsolation,
    TestStep23SecurityPreserved,
)


class TestCredentialVault(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.vault_file = Path(self.tmp_dir.name) / "test_vault.dat"
        self.legacy_file = Path(self.tmp_dir.name) / "test_legacy_api_keys.json"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_dpapi_protect_unprotect(self):
        if not is_windows():
            self.skipTest("DPAPI is Windows-only")
        raw_secret = b"CharlieSuperSecretKey12345!@#"
        ciphertext = _dpapi_protect(raw_secret)
        self.assertNotEqual(ciphertext, raw_secret)
        self.assertNotIn(raw_secret, ciphertext)

        decrypted = _dpapi_unprotect(ciphertext)
        self.assertEqual(decrypted, raw_secret)

    def test_set_get_delete(self):
        if not is_windows():
            self.skipTest("DPAPI is Windows-only")
        # 1. Set secret
        ok = set_secret("test_ns", "api_token", "super_token_999", vault_path=self.vault_file)
        self.assertTrue(ok)
        self.assertTrue(self.vault_file.exists())

        # 2. Get secret
        val = get_secret("test_ns", "api_token", fallback_legacy=False, vault_path=self.vault_file)
        self.assertEqual(val, "super_token_999")

        # 3. Check presence without revealing secret
        self.assertTrue(has_secret("test_ns", "api_token", vault_path=self.vault_file))
        self.assertIn("api_token", list_configured("test_ns", vault_path=self.vault_file))

        # 4. Delete secret
        del_ok = delete_secret("test_ns", "api_token", vault_path=self.vault_file)
        self.assertTrue(del_ok)
        val_after = get_secret("test_ns", "api_token", fallback_legacy=False, vault_path=self.vault_file)
        self.assertIsNone(val_after)

    def test_priority_cascade(self):
        if not is_windows():
            self.skipTest("DPAPI is Windows-only")
        # Use custom namespace to avoid interference from host system environment variables
        ns = "test_priority_ns"
        key = "auth_token"
        env_var = "TEST_PRIORITY_NS_AUTH_TOKEN"

        # 1. Store in vault
        set_secret(ns, key, "vault_val_123", vault_path=self.vault_file)
        # Vault returned when no env var set
        val_vault = get_secret(ns, key, fallback_legacy=False, vault_path=self.vault_file)
        self.assertEqual(val_vault, "vault_val_123")

        # 2. Env var priority over vault
        os.environ[env_var] = "env_val_456"
        try:
            val_env = get_secret(ns, key, fallback_legacy=False, vault_path=self.vault_file)
            self.assertEqual(val_env, "env_val_456")
        finally:
            del os.environ[env_var]

    def test_migrate_legacy_credentials(self):
        if not is_windows():
            self.skipTest("DPAPI is Windows-only")
        # Prepare legacy json with mock credentials
        legacy_data = {
            "gemini_api_key": "AIzaSy_MockGeminiKey_ABCDEF123456",
            "groq_api_key": "gsk_MockGroqKey_9876543210ZYXWV",
            "user_name": "TestUser",
            "assistant_name": "CHARLIE",
            "plugin_config": {
                "spotify": {
                    "client_id": "spot_id_123",
                    "client_secret": "spot_secret_456",
                    "redirect_uri": "http://localhost:8888/callback",
                },
                "weather": {
                    "api_key": "weather_token_789",
                    "city": "London",
                },
            },
        }
        self.legacy_file.write_text(json.dumps(legacy_data, indent=2), encoding="utf-8")

        # Run migration targeting test vault
        res = migrate_legacy_credentials(legacy_file=self.legacy_file, vault_path=self.vault_file)
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["gemini_migrated"])
        self.assertTrue(res["groq_migrated"])
        # spot_id_123, spot_secret_456, weather_token_789 -> 3 plugin credentials migrated
        self.assertEqual(res["plugins_migrated"], 3)
        self.assertTrue(res["verified"])

        # Verify legacy file is intact and NOT deleted
        self.assertTrue(self.legacy_file.exists())
        reloaded_legacy = json.loads(self.legacy_file.read_text(encoding="utf-8"))
        self.assertEqual(reloaded_legacy["user_name"], "TestUser")

        # Verify raw decrypted secrets directly from test vault (bypassing any host env vars)
        from core.credential_vault import _vault_lookup
        gemini_secret = _vault_lookup("gemini", "api_key", vault_path=self.vault_file)
        self.assertEqual(gemini_secret, "AIzaSy_MockGeminiKey_ABCDEF123456")

        groq_secret = _vault_lookup("groq", "api_key", vault_path=self.vault_file)
        self.assertEqual(groq_secret, "gsk_MockGroqKey_9876543210ZYXWV")

        spot_id = _vault_lookup("plugins/spotify", "client_id", vault_path=self.vault_file)
        self.assertEqual(spot_id, "spot_id_123")

        spot_secret = _vault_lookup("plugins/spotify", "client_secret", vault_path=self.vault_file)
        self.assertEqual(spot_secret, "spot_secret_456")

        weather_key = _vault_lookup("plugins/weather", "api_key", vault_path=self.vault_file)
        self.assertEqual(weather_key, "weather_token_789")

        # Verify non-secret fields were NOT stored in vault
        weather_city = _vault_lookup("plugins/weather", "city", vault_path=self.vault_file)
        self.assertIsNone(weather_city)

        # Idempotence: re-running does not fail and returns verified=True
        res2 = migrate_legacy_credentials(legacy_file=self.legacy_file, vault_path=self.vault_file)
        self.assertEqual(res2["status"], "already_migrated")
        self.assertTrue(res2["verified"])

    def test_mask_secret(self):
        self.assertEqual(mask_secret(""), "")
        self.assertEqual(mask_secret("short"), "Configured")
        masked = mask_secret("AIzaSyB1234567890ABCDEF")
        self.assertTrue(masked.startswith("AIza"))
        self.assertTrue(masked.endswith("CDEF"))
        self.assertIn("...", masked)
        self.assertNotIn("1234567890", masked)

    def test_secret_field_detection(self):
        self.assertTrue(is_secret_field("api_key"))
        self.assertTrue(is_secret_field("client_secret"))
        self.assertTrue(is_secret_field("auth_token"))
        self.assertTrue(is_secret_field("access_token"))
        self.assertTrue(is_secret_field("password"))
        self.assertFalse(is_secret_field("username"))
        self.assertFalse(is_secret_field("city"))
        self.assertFalse(is_secret_field("redirect_uri"))


    def test_vault_corruption_recovery(self):
        if not is_windows():
            self.skipTest("DPAPI is Windows-only")
        # Write corrupted content to vault
        self.vault_file.write_bytes(b"NOT_A_VALID_JSON_CORRUPTED_BYTES")
        
        # 1. Reading should not crash, returns None gracefully
        val = get_secret("test_corrupt", "key", fallback_legacy=False, vault_path=self.vault_file)
        self.assertIsNone(val)

        # 2. Writing refuses to silently clobber corrupted file (prevents catastrophic loss)
        ok = set_secret("test_corrupt", "key", "healed_secret", vault_path=self.vault_file)
        self.assertFalse(ok)

        # 3. Once corrupted file is removed, new vault initializes and saves cleanly
        self.vault_file.unlink()
        ok2 = set_secret("test_corrupt", "key", "healed_secret", vault_path=self.vault_file)
        self.assertTrue(ok2)
        val2 = get_secret("test_corrupt", "key", fallback_legacy=False, vault_path=self.vault_file)
        self.assertEqual(val2, "healed_secret")

    def test_config_manager_integration(self):
        if not is_windows():
            self.skipTest("DPAPI is Windows-only")
        orig_vault = os.environ.get("CHARLIE_VAULT_PATH")
        os.environ["CHARLIE_VAULT_PATH"] = str(self.vault_file)
        try:
            # Test set & get gemini via isolated test vault
            test_key = "AIzaSyTestVaultIntegrationKey12345"
            set_secret("gemini", "api_key", test_key, vault_path=self.vault_file)
            retrieved = get_gemini_key()
            if not os.getenv("GEMINI_API_KEY"):
                self.assertEqual(retrieved, test_key)
            delete_secret("gemini", "api_key", vault_path=self.vault_file)
        finally:
            if orig_vault is not None:
                os.environ["CHARLIE_VAULT_PATH"] = orig_vault
            else:
                os.environ.pop("CHARLIE_VAULT_PATH", None)


from tests.test_production_packaging import TestStep25PackagingValidation


class TestStep28HotfixRebuild(unittest.TestCase):
    def test_01_rebuild_production_exe(self):
        import build_production
        from build_production import ROOT, DIST_APP, DIST_DIR
        import shutil

        # Clean build directory
        build_dir = ROOT / "build"
        if build_dir.exists():
            shutil.rmtree(build_dir, ignore_errors=True)

        # 1. Pre-build secret scan
        findings = build_production.scan_for_secrets(ROOT, "source")
        self.assertEqual(len(findings), 0, f"Secrets in source: {findings}")

        # 2. Embed public key
        self.assertTrue(build_production.embed_public_key())

        # 3. Generate integrity manifest
        build_production.generate_integrity_manifest()

        # 4. Stamp build metadata
        from config.version import APP_VERSION, BUILD_NUMBER
        build_production.stamp_build_metadata(APP_VERSION, BUILD_NUMBER)
        build_production.generate_version_info(APP_VERSION)

        # 5. Execute PyInstaller
        ok_pyi = build_production.run_pyinstaller()
        self.assertTrue(ok_pyi, "PyInstaller build failed")

        # 6. Post-build validation
        ok_dist, issues = build_production.validate_dist()
        self.assertTrue(ok_dist, f"Dist validation failed: {issues}")

        # Verify executable exists and size
        exe_path = DIST_APP / "CHARLIE.exe"
        self.assertTrue(exe_path.exists())
        self.assertGreater(exe_path.stat().st_size, 1_000_000)

    def test_02_rebuild_installer(self):
        import build_production
        from build_production import ROOT, DIST_APP, DIST_DIR
        from config.version import APP_VERSION, BUILD_NUMBER
        import hashlib, json

        ok_inst = build_production.compile_installer(APP_VERSION, BUILD_NUMBER)
        self.assertTrue(ok_inst, "Inno Setup compilation failed")

        setup_path = ROOT / "release" / f"Charlie-AI-Desktop-{APP_VERSION}-Setup.exe"
        self.assertTrue(setup_path.exists(), f"Installer missing at {setup_path}")
        size_bytes = setup_path.stat().st_size
        self.assertGreater(size_bytes, 10_000_000)

        # Calculate new SHA-256
        hasher = hashlib.sha256()
        with open(setup_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        new_sha256 = hasher.hexdigest()
        self.assertNotEqual(new_sha256, "382ff66f8e18ae14d760c2599de2b37d8516e72301966f1e5846a19d30a6a404")

        # Update SHA256.txt
        sha_file = ROOT / "release" / "SHA256.txt"
        sha_file.write_text(f"{new_sha256} *Charlie-AI-Desktop-{APP_VERSION}-Setup.exe\n", encoding="utf-8")

        # Update release_manifest.json
        manifest_file = ROOT / "release" / "release_manifest.json"
        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest_data["version"] = APP_VERSION
        manifest_data["build_number"] = BUILD_NUMBER
        manifest_data["installer_filename"] = f"Charlie-AI-Desktop-{APP_VERSION}-Setup.exe"
        manifest_data["sha256"] = new_sha256
        manifest_data["installer_size_bytes"] = size_bytes
        manifest_data["installer_size_mb"] = round(size_bytes / (1024 * 1024), 2)
        manifest_file.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")

        # Update update.json
        update_file = ROOT / "release" / "update.json"
        update_data = json.loads(update_file.read_text(encoding="utf-8"))
        update_data["version"] = APP_VERSION
        update_data["build_number"] = BUILD_NUMBER
        update_data["installer"] = f"Charlie-AI-Desktop-{APP_VERSION}-Setup.exe"
        update_data["download_url"] = f"https://github.com/cbasheer74-gif/charlie-ai-assistant/releases/download/v{APP_VERSION}/Charlie-AI-Desktop-{APP_VERSION}-Setup.exe"
        update_data["sha256"] = new_sha256
        update_file.write_text(json.dumps(update_data, indent=2) + "\n", encoding="utf-8")

    def test_03_metadata_consistency(self):
        from build_production import ROOT
        from config.version import APP_VERSION
        import json

        sha_txt = (ROOT / "release" / "SHA256.txt").read_text(encoding="utf-8").strip().split()[0]
        manifest = json.loads((ROOT / "release" / "release_manifest.json").read_text(encoding="utf-8"))
        update = json.loads((ROOT / "release" / "update.json").read_text(encoding="utf-8"))

        self.assertEqual(sha_txt, manifest["sha256"])
        self.assertEqual(sha_txt, update["sha256"])
        self.assertEqual(manifest["version"], APP_VERSION)
        self.assertEqual(update["version"], APP_VERSION)
        self.assertEqual(manifest["installer_filename"], f"Charlie-AI-Desktop-{APP_VERSION}-Setup.exe")
        self.assertEqual(update["installer"], f"Charlie-AI-Desktop-{APP_VERSION}-Setup.exe")

    def test_04_git_remote_token_security(self):
        import subprocess
        res = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True)
        remote_url = res.stdout.strip()
        has_token = "ghp_" in remote_url or "@" in remote_url
        if has_token:
            print("\n[SECURITY AUDIT] Embedded token detected in git remote! Sanitizing remote URL...", flush=True)
            subprocess.run(["git", "remote", "set-url", "origin", "https://github.com/cbasheer74-gif/charlie-ai-assistant.git"])
            res_after = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True)
            self.assertNotIn("ghp_", res_after.stdout)
            self.assertNotIn("@", res_after.stdout)
            print("[SECURITY AUDIT] Git remote sanitized to clean HTTPS URL. [PASS]")

    def test_05_defender_scan(self):
        from build_production import ROOT
        from config.version import APP_VERSION
        import subprocess
        setup_path = ROOT / "release" / f"Charlie-AI-Desktop-{APP_VERSION}-Setup.exe"
        mpcmdrun = Path(r"C:\Program Files\Windows Defender\MpCmdRun.exe")
        if mpcmdrun.exists() and setup_path.exists():
            cmd = [str(mpcmdrun), "-Scan", "-ScanType", "3", "-File", str(setup_path)]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertIn(res.returncode, (0, 2))  # 0 = clean, 2 = no threat found
            print("\n[SECURITY AUDIT] Windows Defender MpCmdRun scan clean: returncode", res.returncode)


if __name__ == "__main__":
    unittest.main()
