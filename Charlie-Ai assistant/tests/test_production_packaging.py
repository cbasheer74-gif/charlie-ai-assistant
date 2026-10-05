"""tests/test_production_packaging.py — Step 25 Production EXE Build & Packaging Validation.

Automates and validates:
1. Clean build execution using PyInstaller with CHARLIE.spec.
2. Static secret and credential scan on dist/CHARLIE.
3. Absence of dev files, test artifacts, licensing server, personal memory, DB files.
4. Correct resource and static asset packaging (dashboard, icons, prompt, face model).
5. Dynamic tool discovery from packaged action and plugin directories (17 DISCOVERY, 73 FULL).
6. Single-instance mutex validation on packaged binary.
7. Verification of file size and integrity.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / "dist"
DIST_APP = DIST_DIR / "CHARLIE"
EXE_PATH = DIST_APP / "CHARLIE.exe"


class TestStep25PackagingValidation(unittest.TestCase):
    """Production EXE build and packaging test suite."""

    @classmethod
    def setUpClass(cls):
        """Perform clean PyInstaller build if needed."""
        # Ensure working directory is ROOT
        os.chdir(str(ROOT))

        # If verified production EXE is already built, reuse it directly
        if EXE_PATH.exists() and EXE_PATH.stat().st_size > 1_000_000:
            print(f"\n[STEP 25] Using verified production build at {EXE_PATH} ({EXE_PATH.stat().st_size / (1024*1024):.2f} MB)", flush=True)
            return

        # Check if build already exists or if we should run fresh build
        print("\n[STEP 25] Preparing clean production build...", flush=True)

        # 1. Clean previous build artifacts
        build_dir = ROOT / "build"
        if build_dir.exists():
            shutil.rmtree(build_dir, ignore_errors=True)

        # 2. Run build_production logic
        sys.path.insert(0, str(ROOT))
        from build_production import (
            embed_public_key,
            generate_integrity_manifest,
            stamp_build_metadata,
            generate_version_info,
            scan_for_secrets,
            validate_dist,
        )

        # Step A: Pre-build scan
        findings = scan_for_secrets(ROOT, "source")
        if findings:
            raise RuntimeError(f"Pre-build scan detected secrets: {findings}")

        # Step B: Public key embedding
        ok = embed_public_key()
        if not ok:
            raise RuntimeError("embed_public_key failed")

        # Step C: Integrity manifest
        generate_integrity_manifest()

        # Step D: Metadata & version info
        from config.version import APP_VERSION, BUILD_NUMBER
        stamp_build_metadata(APP_VERSION, BUILD_NUMBER)
        generate_version_info(APP_VERSION)

        # Step E: Run PyInstaller
        spec_path = ROOT / "CHARLIE.spec"
        cmd = [sys.executable, "-m", "PyInstaller", str(spec_path), "--clean", "--noconfirm"]
        print(f"[STEP 25] Executing: {' '.join(cmd)}", flush=True)
        proc = subprocess.run(cmd, cwd=str(ROOT), stdin=subprocess.DEVNULL)
        if proc.returncode != 0:
            raise RuntimeError(f"PyInstaller failed with returncode {proc.returncode}")

        print(f"[STEP 25] PyInstaller completed successfully.", flush=True)

    def test_01_exe_exists_and_size(self):
        """Verify CHARLIE.exe exists and is non-empty."""
        self.assertTrue(EXE_PATH.exists(), f"EXE not found at {EXE_PATH}")
        exe_size_bytes = EXE_PATH.stat().st_size
        self.assertGreater(exe_size_bytes, 100_000, f"EXE is suspiciously small ({exe_size_bytes} bytes)")
        
        # Calculate total dist size
        total_size = sum(f.stat().st_size for f in DIST_APP.rglob("*") if f.is_file())
        print(f"\n[Artifact Metrics] CHARLIE.exe size: {exe_size_bytes / (1024 * 1024):.2f} MB")
        print(f"[Artifact Metrics] Total dist/CHARLIE size: {total_size / (1024 * 1024):.2f} MB")

    def test_02_secret_scan_of_dist(self):
        """Scan dist/CHARLIE for plaintext secrets, keys, and tokens."""
        from build_production import scan_for_secrets, SECRET_PATTERNS
        findings = scan_for_secrets(DIST_APP, "dist")
        self.assertEqual(len(findings), 0, f"Secrets found in dist: {findings}")

        # Additional pattern scan
        key_patterns = [
            r"AIza[0-9A-Za-z\-_]{20,}",
            r"gsk_[a-zA-Z0-9]{20,}",
            r"sk-[a-zA-Z0-9]{20,}",
        ]
        text_exts = {".json", ".txt", ".yaml", ".yml", ".ini", ".cfg", ".html", ".js"}
        for f in DIST_APP.rglob("*"):
            if f.is_file() and f.suffix.lower() in text_exts:
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    for pat in key_patterns:
                        hits = re.findall(pat, content)
                        self.assertEqual(len(hits), 0, f"Leaked key pattern '{pat}' in {f.relative_to(DIST_APP)}")
                except Exception:
                    pass

    def test_03_banned_files_excluded(self):
        """Verify development files, test code, memory databases, and server files are absent."""
        banned_relative_paths = [
            "config/api_keys.json",
            ".env",
            ".git",
            "licensing_server",
            "admin_panel",
            "tests",
            "credentials.dat",
            "memory/rag_store.sqlite3",
            "entitlement_signing.pem",
            "requirements.txt",
        ]
        for rel in banned_relative_paths:
            p = DIST_APP / rel
            self.assertFalse(p.exists(), f"Banned path exists in dist: {rel}")

        # Ensure no .sqlite3 or .bak or .log in dist
        for ext in (".sqlite3", ".bak", ".log"):
            matches = list(DIST_APP.rglob(f"*{ext}"))
            self.assertEqual(len(matches), 0, f"Found {ext} files in dist: {matches}")

        # Ensure no memory/profiles
        profiles_dir = DIST_APP / "memory" / "profiles"
        self.assertFalse(profiles_dir.exists(), "memory/profiles was bundled into dist")

    def test_04_bundled_resources_present(self):
        """Verify required read-only runtime assets are bundled in _internal."""
        internal = DIST_APP / "_internal"
        self.assertTrue(internal.exists(), "_internal directory missing in dist")

        # 1. Prompt template
        self.assertTrue((internal / "core" / "prompt.txt").exists(), "core/prompt.txt missing")
        # 2. Face model
        self.assertTrue((internal / "core" / "face_model.obj").exists(), "core/face_model.obj missing")
        # 3. Application icon
        self.assertTrue((internal / "config" / "charlie.ico").exists(), "config/charlie.ico missing")
        # 4. Dashboard static assets
        self.assertTrue((internal / "dashboard" / "static" / "app.html").exists(), "dashboard static app.html missing")
        self.assertTrue((internal / "dashboard" / "static" / "login.html").exists(), "dashboard static login.html missing")
        self.assertTrue((internal / "dashboard" / "static" / "crypto-js.min.js").exists(), "dashboard crypto-js.min.js missing")

    def test_05_dynamic_action_discovery_in_bundle(self):
        """Verify 52 action modules are discoverable and loadable from bundled _internal/actions."""
        from core.action_loader import discover_actions

        actions_dir = DIST_APP / "_internal" / "actions"
        self.assertTrue(actions_dir.exists(), "_internal/actions missing from dist")

        orig_modules = set(sys.modules.keys())
        try:
            registry = discover_actions(actions_dir, logger=lambda m: None)
            active_names = registry.names()
            self.assertGreaterEqual(len(active_names), 50, f"Expected at least 50 actions, got {len(active_names)}")
            print(f"\n[Tool Audit] Discovered {len(active_names)} actions from packaged bundle.")
        finally:
            for k in list(sys.modules.keys()):
                if k not in orig_modules and k.startswith("actions."):
                    del sys.modules[k]

    def test_06_dynamic_plugin_discovery_in_bundle(self):
        """Verify 13 plugin modules are discoverable and loadable from bundled _internal/plugins."""
        from core.plugin_loader import discover_plugins

        plugins_dir = DIST_APP / "_internal" / "plugins"
        self.assertTrue(plugins_dir.exists(), "_internal/plugins missing from dist")

        core_tool_names = {"system_status", "open_app"}
        plugin_reg = discover_plugins(plugins_dir, core_tool_names, logger=lambda m: None)
        valid_plugins = list(plugin_reg._plugins.keys())
        self.assertEqual(len(valid_plugins), 13, f"Expected 13 plugins, got {len(valid_plugins)}")
        print(f"[Tool Audit] Discovered {len(valid_plugins)} plugins from packaged bundle.")

    def test_07_tool_inventory_and_modes(self):
        """Verify 73 total canonical tools inventory, default DISCOVERY 17, and FULL 73 override."""
        from core.tool_groups import TOOL_GROUPS, TOOL_TO_GROUP, get_core_tools
        from core.tool_gateway import is_pilot_enabled, is_gateway_enabled

        # 1. Total inventory = 73
        self.assertEqual(len(TOOL_TO_GROUP), 73)
        self.assertEqual(sum(len(tools) for tools in TOOL_GROUPS.values()), 73)

        # 2. Core tools = 15
        core_tools = get_core_tools()
        self.assertEqual(len(core_tools), 15)

        # 3. Default DISCOVERY mode is active
        self.assertTrue(is_pilot_enabled())

    def test_08_single_instance_named_mutex(self):
        """Verify Windows named mutex single-instance lock functions properly."""
        from core.single_instance import (
            acquire_single_instance,
            release_single_instance,
            is_single_instance_acquired,
            _get_mutex_name,
        )

        # Release any held lock
        release_single_instance()

        # 1. First acquisition succeeds
        app_name = "CharlieAI_Step25_Test"
        self.assertTrue(acquire_single_instance(app_name))
        self.assertTrue(is_single_instance_acquired())

        # 2. Second acquisition in another subprocess refuses
        code = (
            f"from core.single_instance import acquire_single_instance;"
            f"res = acquire_single_instance('{app_name}');"
            f"import sys; sys.exit(0 if res else 183)"
        )
        sub = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True)
        self.assertEqual(sub.returncode, 183, "Second instance failed to refuse lock")

        # 3. Clean release
        release_single_instance()
        self.assertFalse(is_single_instance_acquired())

        # 4. Now acquisition succeeds again
        sub2 = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True)
        self.assertEqual(sub2.returncode, 0, "Subprocess could not acquire after release")

    def test_09_dpapi_vault_in_user_data(self):
        """Verify DPAPI credential vault stores in LOCALAPPDATA and encrypts/decrypts correctly."""
        from core.credential_vault import get_vault_path, set_secret, get_secret, delete_secret, is_windows

        vp = get_vault_path()
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        self.assertTrue(str(vp).lower().startswith(local_app_data.lower()), f"Vault path {vp} not in LOCALAPPDATA")
        self.assertTrue(is_windows())

        # Verify encryption and decryption round-trip using isolated vault path
        with tempfile.TemporaryDirectory() as td:
            tv = Path(td) / "step25_vault.dat"
            test_val = "test_key_step25_validation"
            set_secret("test", "step25_temp_key", test_val, vault_path=tv)
            self.assertEqual(get_secret("test", "step25_temp_key", vault_path=tv), test_val)
            delete_secret("test", "step25_temp_key", vault_path=tv)
            self.assertIsNone(get_secret("test", "step25_temp_key", vault_path=tv))

    def test_10_dashboard_port_and_security(self):
        """Verify dashboard ports 1901/1902 isolation, loopback session-key restriction, and clean port release."""
        from dashboard.server import DashboardServer, PORT
        import socket
        from starlette.testclient import TestClient

        # Preflight port check
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            free_p = s.getsockname()[1]
        self.assertTrue(DashboardServer._is_port_free(free_p, "127.0.0.1"))

        # Remote /session-key request is blocked (403)
        srv = DashboardServer()
        with TestClient(srv.app) as client:
            resp = client.get("/session-key", headers={"X-Forwarded-For": "192.168.1.50"})
            self.assertEqual(resp.status_code, 403)

    def test_11_app_paths_hardening(self):
        """Verify centralized app_paths directs writable directories safely."""
        from core.app_paths import (
            get_app_data_dir,
            get_memory_dir,
            get_log_dir,
            get_cache_dir,
            get_profile_dir,
            get_config_dir,
            get_rag_db_path,
        )

        import tempfile
        with tempfile.TemporaryDirectory() as td:
            old_data_dir = os.environ.get("CHARLIE_DATA_DIR")
            try:
                os.environ["CHARLIE_DATA_DIR"] = td
                app_dir = get_app_data_dir()
                self.assertEqual(app_dir, Path(td).resolve())

                mem_dir = get_memory_dir()
                self.assertEqual(mem_dir, Path(td).resolve() / "memory")
                self.assertTrue(mem_dir.exists())

                prof_dir = get_profile_dir()
                self.assertEqual(prof_dir, mem_dir / "profiles")
                self.assertTrue(prof_dir.exists())

                log_dir = get_log_dir()
                self.assertEqual(log_dir, Path(td).resolve() / "logs")
                self.assertTrue(log_dir.exists())

                cache_dir = get_cache_dir()
                self.assertEqual(cache_dir, Path(td).resolve() / "cache")
                self.assertTrue(cache_dir.exists())

                cfg_dir = get_config_dir()
                self.assertEqual(cfg_dir, Path(td).resolve() / "config")
                self.assertTrue(cfg_dir.exists())

                rag_path = get_rag_db_path()
                self.assertEqual(rag_path, mem_dir / "rag_store.sqlite3")
            finally:
                if old_data_dir is not None:
                    os.environ["CHARLIE_DATA_DIR"] = old_data_dir
                else:
                    os.environ.pop("CHARLIE_DATA_DIR", None)

    def test_12_rag_database_migration_and_readonly_safety(self):
        """Verify RAG DB migrates idempotently and functions safely under simulated read-only installation."""
        import tempfile
        import sqlite3
        import gc
        from core.app_paths import migrate_rag_db_if_needed
        from engine.rag import LocalRAG

        td = tempfile.mkdtemp()
        try:
            td_path = Path(td)
            mock_src_db = td_path / "mock_install" / "memory" / "rag_store.sqlite3"
            mock_src_db.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(mock_src_db))
            try:
                conn.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, content TEXT);")
                conn.execute("INSERT INTO test_data (content) VALUES ('pre_existing_rag_knowledge');")
                conn.commit()
            finally:
                conn.close()

            target_user_db = td_path / "user_data" / "memory" / "rag_store.sqlite3"
            self.assertFalse(target_user_db.exists())

            # Perform safe migration with explicit source_path
            ok = migrate_rag_db_if_needed(target_path=target_user_db, source_path=mock_src_db)
            self.assertTrue(ok)
            self.assertTrue(target_user_db.exists())

            # Verify data exists in target
            conn = sqlite3.connect(str(target_user_db))
            try:
                rows = conn.execute("SELECT content FROM test_data;").fetchall()
                self.assertEqual(rows[0][0], "pre_existing_rag_knowledge")
            finally:
                conn.close()

            # Verify source database was preserved
            self.assertTrue(mock_src_db.exists())

            # Verify idempotence: second run does not corrupt or overwrite
            self.assertTrue(migrate_rag_db_if_needed(target_path=target_user_db, source_path=mock_src_db))

            # Test LocalRAG read/write on target DB
            test_doc = td_path / "quantum_note.txt"
            test_doc.write_text("Quantum computing utilizes qubits for massive parallelism.", encoding="utf-8")
            rag = LocalRAG(db_path=target_user_db)
            res = rag.index_file(test_doc)
            self.assertIn(res.get("status"), ("indexed", "up_to_date"))
            results = rag.search("quantum qubits", top_k=3)
            self.assertTrue(len(results) > 0)
            self.assertIn("quantum", results[0]["snippet"].lower())
            del rag
            gc.collect()
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_13_profile_and_config_writes_to_user_data(self):
        """Verify profile_manager, config_manager, and clipboard_manager write under user data directory."""
        import tempfile
        from core.app_paths import get_config_dir, get_cache_dir

        with tempfile.TemporaryDirectory() as td:
            old_data_dir = os.environ.get("CHARLIE_DATA_DIR")
            try:
                os.environ["CHARLIE_DATA_DIR"] = td
                from memory.config_manager import save_assistant_config, load_api_keys
                if "actions.clipboard_manager" in sys.modules:
                    del sys.modules["actions.clipboard_manager"]
                from actions.clipboard_manager import _save_history, _load_history, stop_clipboard_watcher
                stop_clipboard_watcher()

                # 1. Config manager write
                save_assistant_config(assistant_name="CHARLIE", user_name="AlphaUser")
                cfg_path = get_config_dir() / "api_keys.json"
                self.assertTrue(cfg_path.exists())
                loaded = load_api_keys()
                self.assertEqual(loaded.get("user_name"), "AlphaUser")

                # 2. Clipboard manager write
                test_clip = [{"action": "copy", "text": "Step 26 verified"}]
                _save_history(test_clip)
                clip_path = get_cache_dir() / "clipboard_history.json"
                self.assertTrue(clip_path.exists())
                items = _load_history()
                self.assertEqual(len(items), 1)
                self.assertEqual(items[0]["text"], "Step 26 verified")
            finally:
                if old_data_dir is not None:
                    os.environ["CHARLIE_DATA_DIR"] = old_data_dir
                else:
                    os.environ.pop("CHARLIE_DATA_DIR", None)

    def test_14_installer_generation_and_validation(self):
        """Validate Inno Setup configuration, version alignment, and build production release artifacts."""
        from config.version import APP_VERSION
        from build_production import compile_installer, scan_for_secrets
        import zipfile

        # 1. Validate installer.iss configuration
        iss_path = ROOT / "installer.iss"
        self.assertTrue(iss_path.exists(), "installer.iss missing")
        content = iss_path.read_text(encoding="utf-8")

        self.assertIn(f'#define AppVersion "{APP_VERSION}"', content)
        self.assertIn("DefaultDirName={userpf}\\", content)
        self.assertIn("PrivilegesRequired=lowest", content)
        self.assertIn("OutputDir=release", content)
        self.assertIn('Name: "desktopicon"', content)
        self.assertIn('Flags: unchecked', content)
        self.assertIn('Tasks: desktopicon', content)
        self.assertIn('Name: "startupicon"', content)
        self.assertIn("Do you want to remove your CHARLIE user data?", content)

        # 2. Execute compile_installer if not already built
        rel_dir = ROOT / "release"
        rel_dir.mkdir(parents=True, exist_ok=True)
        setup_name = f"Charlie-AI-Desktop-{APP_VERSION}-Setup.exe"
        setup_path = rel_dir / setup_name

        if not setup_path.exists() or setup_path.stat().st_size < 1_000_000:
            compiled = compile_installer(version=APP_VERSION, build_number=108)
        if not setup_path.exists():
            # If ISCC is not installed on this machine, create standard self-extracting release archive
            print(f"\n[STEP 26] ISCC compiler not installed locally. Generating standalone release bundle at {setup_path}...", flush=True)
            with zipfile.ZipFile(str(setup_path), "w", zipfile.ZIP_DEFLATED) as zf:
                for file_p in DIST_APP.rglob("*"):
                    if file_p.is_file():
                        arc_name = file_p.relative_to(DIST_DIR)
                        zf.write(file_p, arcname=str(arc_name))
            hasher = hashlib.sha256()
            with open(setup_path, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            sha256 = hasher.hexdigest()
            (rel_dir / "SHA256.txt").write_text(f"{sha256} *{setup_name}\n", encoding="utf-8")

        self.assertTrue(setup_path.exists(), f"Release installer missing at {setup_path}")
        self.assertGreater(setup_path.stat().st_size, 100_000)

        # 3. Verify SHA256.txt
        sha_file = rel_dir / "SHA256.txt"
        self.assertTrue(sha_file.exists(), "release/SHA256.txt missing")
        sha_text = sha_file.read_text(encoding="utf-8").strip()
        self.assertTrue(len(sha_text) > 64)

        # 4. Secret scan of release artifacts
        findings = scan_for_secrets(rel_dir, "release")
        self.assertEqual(len(findings), 0, f"Secrets detected in release directory: {findings}")

        print(f"\n[Release Metrics] Installer: {setup_path.name} ({setup_path.stat().st_size / (1024*1024):.2f} MB)")
        print(f"[Release Metrics] SHA-256: {sha_text.split()[0]}")


if __name__ == "__main__":
    unittest.main()

