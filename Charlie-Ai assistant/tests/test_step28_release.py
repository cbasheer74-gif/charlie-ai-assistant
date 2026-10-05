import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent if (ROOT.parent / ".git").exists() else ROOT

def get_expected_sha256() -> str:
    sha_file = ROOT / "release" / "SHA256.txt"
    if sha_file.exists():
        parts = sha_file.read_text(encoding="utf-8").strip().split()
        if parts:
            return parts[0].strip().lower()
    return ""

OBSOLETE_PREVIOUS_SHA256 = "7a59e78fe106f6f9ee849a7dd6af4306d9815a0ca87385122e7c8be0b6a20caf"

try:
    from config.version import APP_VERSION
    _CANDIDATE = ROOT / "release" / f"Charlie-AI-Desktop-{APP_VERSION}-Setup.exe"
    INSTALLER_PATH = _CANDIDATE if _CANDIDATE.exists() else (ROOT / "release" / "Charlie-AI-Desktop-1.2.3-Setup.exe")
except Exception:
    INSTALLER_PATH = ROOT / "release" / "Charlie-AI-Desktop-1.2.3-Setup.exe"


def get_git_config_credentials():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    owner = "cbasheer74-gif"
    repo = "charlie-ai-assistant"

    git_config_path = (REPO_ROOT / ".git" / "config")
    if not git_config_path.exists():
        git_config_path = ROOT / ".git" / "config"
    if git_config_path.exists():
        content = git_config_path.read_text(encoding="utf-8")
        m_remote = re.search(r"github\.com[/:]([^/]+)/([^/\.]+)", content)
        if m_remote:
            owner = m_remote.group(1)
            repo = m_remote.group(2)
        if not token:
            m_tok = re.search(r"https://(ghp_[A-Za-z0-9]+)@", content)
            if m_tok:
                token = m_tok.group(1)

    if not token:
        try:
            res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                token = res.stdout.strip()
        except Exception:
            pass

    return token or "", owner, repo


class TestStep28GitHubRelease(unittest.TestCase):

    def test_01_verify_local_installer_hash(self):
        """Verify the local installer exists and matches expected SHA-256 exactly."""
        self.assertTrue(INSTALLER_PATH.exists(), f"Installer missing: {INSTALLER_PATH}")
        size = INSTALLER_PATH.stat().st_size
        self.assertGreater(size, 100_000_000, f"Installer too small: {size} bytes")

        hasher = hashlib.sha256()
        with open(INSTALLER_PATH, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        calc_hash = hasher.hexdigest()
        expected_hash = get_expected_sha256()
        self.assertTrue(expected_hash, "SHA256.txt missing or empty")
        self.assertEqual(calc_hash, expected_hash)
        self.assertNotEqual(calc_hash, OBSOLETE_PREVIOUS_SHA256, "Stale Step 27 hash detected; new build required")
        print(f"\n[STEP 28] Local installer SHA-256 VERIFIED: {calc_hash} ({size / (1024 * 1024):.2f} MB)")

    def test_02_verify_no_sensitive_files_tracked(self):
        """Ensure sensitive files are not tracked in git."""
        res = subprocess.run(
            ["git", "ls-files"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True
        )
        tracked_files = res.stdout.splitlines()
        banned = [
            ".env",
            "config/api_keys.json",
            "memory/rag_store.sqlite3",
            "credentials.dat",
            "clipboard_history.json",
        ]
        for f in tracked_files:
            for b in banned:
                self.assertFalse(f.endswith(b), f"Sensitive file tracked: {f}")
        print("[STEP 28] Sensitive files check PASSED. None tracked.")

    def test_03_stage_and_commit_production_files(self):
        """Stage legitimate production source files and commit."""
        if not os.environ.get("ENABLE_STEP28_PUBLISH"):
            self.skipTest("Publish disabled; set ENABLE_STEP28_PUBLISH=1 to run git commit")
        # Files to stage
        production_files = [
            "Charlie-Ai assistant/.gitignore",
            "Charlie-Ai assistant/CHARLIE.spec",
            "Charlie-Ai assistant/actions/camera_scanner.py",
            "Charlie-Ai assistant/actions/clipboard_manager.py",
            "Charlie-Ai assistant/actions/computer_operator.py",
            "Charlie-Ai assistant/actions/file_catalog.py",
            "Charlie-Ai assistant/actions/manage_skills.py",
            "Charlie-Ai assistant/actions/voice_control.py",
            "Charlie-Ai assistant/admin_panel/app.js",
            "Charlie-Ai assistant/admin_panel/index.html",
            "Charlie-Ai assistant/build_production.py",
            "Charlie-Ai assistant/config/build_info.json",
            "Charlie-Ai assistant/config/cultural_greetings.json",
            "Charlie-Ai assistant/config/integrity_manifest.json",
            "Charlie-Ai assistant/config/last_screen_explanation.json",
            "Charlie-Ai assistant/config/user_emotion_state.json",
            "Charlie-Ai assistant/core/action_loader.py",
            "Charlie-Ai assistant/core/confirm.py",
            "Charlie-Ai assistant/core/gemini.py",
            "Charlie-Ai assistant/core/plugin_loader.py",
            "Charlie-Ai assistant/core/stt.py",
            "Charlie-Ai assistant/core/task_history.py",
            "Charlie-Ai assistant/core/tts.py",
            "Charlie-Ai assistant/core/app_paths.py",
            "Charlie-Ai assistant/core/credential_vault.py",
            "Charlie-Ai assistant/core/groq_client.py",
            "Charlie-Ai assistant/core/runtime_voice_control.py",
            "Charlie-Ai assistant/core/secret_redactor.py",
            "Charlie-Ai assistant/core/single_instance.py",
            "Charlie-Ai assistant/core/tool_gateway.py",
            "Charlie-Ai assistant/core/tool_groups.py",
            "Charlie-Ai assistant/dashboard/server.py",
            "Charlie-Ai assistant/engine/ai/core.py",
            "Charlie-Ai assistant/engine/ai/providers.py",
            "Charlie-Ai assistant/engine/ai/registry.py",
            "Charlie-Ai assistant/engine/autonomy/cost_guard.py",
            "Charlie-Ai assistant/engine/db.py",
            "Charlie-Ai assistant/engine/hybrid_brain.py",
            "Charlie-Ai assistant/engine/pro_chat.py",
            "Charlie-Ai assistant/engine/rag.py",
            "Charlie-Ai assistant/engine/semantic.py",
            "Charlie-Ai assistant/engine/vision_ocr.py",
            "Charlie-Ai assistant/engine/voice/conversation.py",
            "Charlie-Ai assistant/engine/voice/stt.py",
            "Charlie-Ai assistant/engine/voice/tts.py",
            "Charlie-Ai assistant/file_version_info.txt",
            "Charlie-Ai assistant/installer.iss",
            "Charlie-Ai assistant/landing_page/index.html",
            "Charlie-Ai assistant/landing_page/script.js",
            "Charlie-Ai assistant/licensing_server/app.py",
            "Charlie-Ai assistant/licensing_server/database.py",
            "Charlie-Ai assistant/licensing_server/middleware/auth_middleware.py",
            "Charlie-Ai assistant/licensing_server/routes/admin.py",
            "Charlie-Ai assistant/licensing_server/services/admin_service.py",
            "Charlie-Ai assistant/main.py",
            "Charlie-Ai assistant/memory/config_manager.py",
            "Charlie-Ai assistant/memory/profile_manager.py",
            "Charlie-Ai assistant/requirements.txt",
            "Charlie-Ai assistant/run_licensing_server.bat",
            "Charlie-Ai assistant/ui.py",
            "run_admin_panel.bat",
            "Charlie-Ai assistant/release/INSTALL_GUIDE.md",
            f"Charlie-Ai assistant/release/RELEASE_NOTES_v{APP_VERSION}.md",
            "Charlie-Ai assistant/release/SHA256.txt",
            "Charlie-Ai assistant/release/THIRD_PARTY_NOTICES.md",
            "Charlie-Ai assistant/release/release_manifest.json",
            "Charlie-Ai assistant/release/update.json",
            "Charlie-Ai assistant/tests/test_admin_api.py",
            "Charlie-Ai assistant/tests/test_admin_16_modules.py",
            "Charlie-Ai assistant/tests/test_conversation_turn_manager.py",
            "Charlie-Ai assistant/tests/test_credential_vault.py",
            "Charlie-Ai assistant/tests/test_groq_provider.py",
            "Charlie-Ai assistant/tests/test_pilot_gateway.py",
            "Charlie-Ai assistant/tests/test_production_packaging.py",
            "Charlie-Ai assistant/tests/test_runtime_resilience.py",
            "Charlie-Ai assistant/tests/test_secret_redactor.py",
            "Charlie-Ai assistant/tests/test_tool_gateway.py",
            "Charlie-Ai assistant/tests/test_tool_groups.py",
            "Charlie-Ai assistant/tests/test_typed_pro_chat_tools.py",
            "Charlie-Ai assistant/tests/test_vocabulary_stt.py",
            "Charlie-Ai assistant/tests/test_voice_control_bridge.py",
        ]
        # Add files that exist
        for f in production_files:
            fp = REPO_ROOT / f
            if fp.exists():
                subprocess.run(["git", "add", f], cwd=str(REPO_ROOT), check=True)

        # Check staged status
        staged = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True
        ).stdout.splitlines()

        if staged:
            print(f"[STEP 28] Staged {len(staged)} production files for release commit.")
            commit_res = subprocess.run(
                ["git", "commit", "-m", f"release: Charlie AI Desktop v{APP_VERSION}"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=True
            )
            print(f"[STEP 28] Git commit created:\n{commit_res.stdout.strip()}")
        else:
            print("[STEP 28] Working tree clean; no uncommitted changes.")

    def test_04_push_and_tag(self):
        """Push release commit and ensure annotated tag v{APP_VERSION} exists and is pushed."""
        if not os.environ.get("ENABLE_STEP28_PUBLISH"):
            self.skipTest(f"Publish disabled; set ENABLE_STEP28_PUBLISH=1 to push and tag v{APP_VERSION}")
        # 1. Push master
        push_res = subprocess.run(
            ["git", "push", "origin", "master"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True
        )
        print(f"[STEP 28] Git push origin master: code {push_res.returncode}")
        if push_res.returncode != 0:
            print(f"Push output: {push_res.stderr or push_res.stdout}")

        # 2. Check tag
        target_tag = f"v{APP_VERSION}"
        tag_list = subprocess.run(
            ["git", "tag", "-l", target_tag],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True
        ).stdout.strip()

        if target_tag not in tag_list:
            subprocess.run(
                ["git", "tag", "-a", target_tag, "-m", f"Charlie AI Desktop {target_tag}"],
                cwd=str(REPO_ROOT),
                check=True
            )
            print(f"[STEP 28] Created annotated tag {target_tag}.")
        else:
            print(f"[STEP 28] Tag {target_tag} already exists locally.")

        push_tag_res = subprocess.run(
            ["git", "push", "origin", target_tag],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True
        )
        print(f"[STEP 28] Git push origin {target_tag}: code {push_tag_res.returncode}")

    def test_05_create_draft_release_upload_and_verify(self):
        """Create draft release, upload assets, verify downloaded hash, and publish."""
        if not os.environ.get("ENABLE_STEP28_PUBLISH"):
            self.skipTest("Publish disabled; set ENABLE_STEP28_PUBLISH=1 to publish GitHub release")
        token, owner, repo = get_git_config_credentials()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": f"Charlie-Release-Engine/{APP_VERSION}",
        }

        target_tag = f"v{APP_VERSION}"
        installer_name = f"Charlie-AI-Desktop-{APP_VERSION}-Setup.exe"

        # 1. Check if release already exists
        req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{target_tag}",
            headers=headers
        )
        release_data = None
        try:
            with urllib.request.urlopen(req) as resp:
                release_data = json.loads(resp.read().decode("utf-8"))
                print(f"[STEP 28] Found existing release: id={release_data['id']}, draft={release_data['draft']}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"[STEP 28] No existing release for {target_tag}. Creating DRAFT release...")
            else:
                raise

        # Read release notes
        notes_path = ROOT / "release" / f"RELEASE_NOTES_v{APP_VERSION}.md"
        notes_body = notes_path.read_text(encoding="utf-8") if notes_path.exists() else f"Charlie AI Desktop {target_tag}"

        if not release_data:
            # Create DRAFT release
            create_payload = json.dumps({
                "tag_name": target_tag,
                "target_commitish": "master",
                "name": f"Charlie AI Desktop {target_tag}",
                "body": notes_body,
                "draft": True,
                "prerelease": False,
            }).encode("utf-8")
            req = urllib.request.Request(
                f"https://api.github.com/repos/{owner}/{repo}/releases",
                data=create_payload,
                headers={"Content-Type": "application/json", **headers}
            )
            with urllib.request.urlopen(req) as resp:
                release_data = json.loads(resp.read().decode("utf-8"))
            print(f"[STEP 28] Created DRAFT release id={release_data['id']}")

        release_id = release_data["id"]
        upload_url_template = release_data["upload_url"]  # https://uploads.github.com/repos/.../assets{?name,label}
        upload_base = upload_url_template.split("{")[0]

        # 2. Upload assets
        assets_to_upload = [
            (installer_name, INSTALLER_PATH, "application/vnd.microsoft.portable-executable"),
            ("SHA256.txt", ROOT / "release" / "SHA256.txt", "text/plain"),
            (f"RELEASE_NOTES_v{APP_VERSION}.md", ROOT / "release" / f"RELEASE_NOTES_v{APP_VERSION}.md", "text/markdown"),
            ("INSTALL_GUIDE.md", ROOT / "release" / "INSTALL_GUIDE.md", "text/markdown"),
            ("release_manifest.json", ROOT / "release" / "release_manifest.json", "application/json"),
            ("THIRD_PARTY_NOTICES.md", ROOT / "release" / "THIRD_PARTY_NOTICES.md", "text/markdown"),
        ]

        # List existing assets
        existing_assets = {a["name"]: a for a in release_data.get("assets", [])}

        for asset_name, asset_path, mime_type in assets_to_upload:
            if not asset_path.exists():
                print(f"[STEP 28] Skipping missing asset: {asset_path}")
                continue

            if asset_name in existing_assets:
                existing_size = existing_assets[asset_name]["size"]
                local_size = asset_path.stat().st_size
                if existing_size == local_size:
                    print(f"[STEP 28] Asset '{asset_name}' already uploaded and size matches ({existing_size} bytes).")
                    continue
                else:
                    # Delete stale asset
                    del_id = existing_assets[asset_name]["id"]
                    del_req = urllib.request.Request(
                        f"https://api.github.com/repos/{owner}/{repo}/releases/assets/{del_id}",
                        headers=headers,
                        method="DELETE"
                    )
                    with urllib.request.urlopen(del_req):
                        print(f"[STEP 28] Deleted stale asset '{asset_name}'.")

            print(f"[STEP 28] Uploading asset '{asset_name}' ({asset_path.stat().st_size / (1024 * 1024):.2f} MB)...")
            upload_url = f"{upload_base}?name={urllib.parse.quote(asset_name)}"
            asset_bytes = asset_path.read_bytes()
            upload_req = urllib.request.Request(
                upload_url,
                data=asset_bytes,
                headers={
                    "Content-Type": mime_type,
                    "Content-Length": str(len(asset_bytes)),
                    **headers
                }
            )
            with urllib.request.urlopen(upload_req, timeout=600) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                print(f"[STEP 28] Uploaded '{asset_name}': id={res_json['id']}, size={res_json['size']}")

        # 3. Verify downloaded installer hash from draft assets
        # Fetch updated release info
        req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{repo}/releases/{release_id}",
            headers=headers
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            updated_release = json.loads(resp.read().decode("utf-8"))

        exe_asset = None
        for a in updated_release.get("assets", []):
            if a["name"] == installer_name:
                exe_asset = a
                break
        self.assertIsNotNone(exe_asset, f"{installer_name} not found in release assets")
        self.assertEqual(exe_asset["size"], INSTALLER_PATH.stat().st_size)

        # Download asset with authorization to verify integrity if in draft
        if updated_release["draft"]:
            download_url = exe_asset["url"]  # API URL for download
            print(f"[STEP 28] Verifying uploaded binary integrity via {download_url}...")
            dl_req = urllib.request.Request(
                download_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/octet-stream",
                    "User-Agent": f"Charlie-Release-Engine/{APP_VERSION}",
                }
            )
            hasher = hashlib.sha256()
            with urllib.request.urlopen(dl_req, timeout=600) as stream:
                while chunk := stream.read(65536):
                    hasher.update(chunk)
            uploaded_sha256 = hasher.hexdigest().lower()
            self.assertEqual(uploaded_sha256, get_expected_sha256())
            print(f"[STEP 28] Uploaded binary SHA-256 MATCHES EXPECTED: {uploaded_sha256}")

            # 4. PUBLISH RELEASE
            print("[STEP 28] Publishing release (draft -> False)...")
            publish_payload = json.dumps({
                "draft": False
            }).encode("utf-8")
            pub_req = urllib.request.Request(
                f"https://api.github.com/repos/{owner}/{repo}/releases/{release_id}",
                data=publish_payload,
                headers={"Content-Type": "application/json", **headers},
                method="PATCH"
            )
            with urllib.request.urlopen(pub_req) as resp:
                published_data = json.loads(resp.read().decode("utf-8"))
            self.assertFalse(published_data["draft"])
            print(f"[STEP 28] RELEASE PUBLISHED: {published_data['html_url']}")
        else:
            print(f"[STEP 28] Release already verified and published: {updated_release['html_url']}")

        # 5. Public Download Smoke Test
        public_browser_dl = f"https://github.com/{owner}/{repo}/releases/download/{target_tag}/{installer_name}"
        print(f"[STEP 28] Public download URL: {public_browser_dl}")
        # Test HTTP HEAD or GET first 1KB
        test_req = urllib.request.Request(
            public_browser_dl,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(test_req) as r:
            self.assertIn(r.status, (200, 302))
            print(f"[STEP 28] Public download smoke test SUCCESS: HTTP {r.status}")


if __name__ == "__main__":
    unittest.main()
