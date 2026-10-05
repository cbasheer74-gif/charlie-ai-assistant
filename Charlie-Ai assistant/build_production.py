"""
build_production.py — Production Build Script for CHARLIE.

Automates:
  1. Pre-build secret scanning (blocks if secrets found in dist)
  2. Integrity manifest generation (SHA256 hashes of critical modules)
  3. Public key embedding into entitlement_verifier.py
  4. Build metadata stamping
  5. PyInstaller build execution
  6. Post-build validation (no .py source, no secrets in output)
  7. Inno Setup compilation (optional)

Usage:
  python build_production.py
  python build_production.py --skip-installer
  python build_production.py --version 1.2.1 --build-number 105
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "dist"
DIST_APP = DIST_DIR / "CHARLIE"
CONFIG_DIR = ROOT / "config"
SERVER_KEYS_DIR = ROOT / "licensing_server" / "keys"
VERIFIER_FILE = ROOT / "engine" / "commercial" / "entitlement_verifier.py"


# ── Secret patterns that MUST NOT appear in dist ─────────────────────────────
SECRET_PATTERNS = [
    r"AIzaSy[A-Za-z0-9_-]{33}",                     # Google API key
    r"sk-[A-Za-z0-9]{32,}",                          # OpenAI key
    r"rzp_(live|test)_[A-Za-z0-9]{14,}",             # Razorpay key
    r"charlie_v1_commercial_license_signing_secret",   # Old HMAC secret
    r"-----BEGIN PRIVATE KEY-----",                   # RSA private key
    r"-----BEGIN RSA PRIVATE KEY-----",               # RSA private key alt
    r"RAZORPAY_KEY_SECRET\s*=\s*\"[^\"]+\"",          # Payment secret assignment
]


def log(msg: str) -> None:
    print(f"[BUILD] {msg}")


def error(msg: str) -> None:
    print(f"[BUILD ERROR] {msg}", file=sys.stderr)


# ── Step 1: Pre-build Secret Scan ────────────────────────────────────────────

def scan_for_secrets(directory: Path, label: str = "source") -> list:
    """Scan directory for leaked secrets. Returns list of findings."""
    findings = []
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", "licensing_server", "tests", "build", "dist", "release", ".system_generated"}
    for root, dirs, files in os.walk(directory):
        # Skip irrelevant dirs
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        if "googleapiclient" in Path(root).parts or "discovery_cache" in Path(root).parts:
            continue
        for fname in files:
            if fname in ("build_production.py", "CHARLIE_RC1_BUILD_AUDIT.md"):
                continue
            if label == "source" and fname in ("api_keys.json", "api_keys.json.example"):
                continue
            if not fname.endswith((".py", ".json", ".txt", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".env")):
                continue
            fpath = Path(root) / fname
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                for pattern in SECRET_PATTERNS:
                    matches = re.findall(pattern, content)
                    if matches:
                        rel = fpath.relative_to(directory)
                        findings.append(f"{label}/{rel}: matched '{pattern}' ({len(matches)} hit(s))")
            except Exception:
                pass
    return findings


# ── Step 2: Embed Public Key ─────────────────────────────────────────────────

def embed_public_key() -> bool:
    """Copy server's RSA public key into the desktop entitlement verifier."""
    pub_key_path = SERVER_KEYS_DIR / "entitlement_verify.pub"
    if not pub_key_path.exists():
        log("No public key found at licensing_server/keys/. Generating keypair...")
        try:
            sys.path.insert(0, str(ROOT))
            from licensing_server.config import ensure_rsa_keypair
            ensure_rsa_keypair()
        except Exception as e:
            error(f"Failed to generate RSA keypair: {e}")
            return False

    if not pub_key_path.exists():
        error("Public key still not found after generation attempt.")
        return False

    public_key_pem = pub_key_path.read_text(encoding="utf-8").strip()

    # Read verifier source
    verifier_src = VERIFIER_FILE.read_text(encoding="utf-8")

    # Replace placeholder or update existing key
    pattern = r'VERIFICATION_PUBLIC_KEY_PEM = """[\s\S]*?""".strip\(\)'
    replacement = f'VERIFICATION_PUBLIC_KEY_PEM = """\n{public_key_pem}\n""".strip()'

    if re.search(pattern, verifier_src):
        verifier_src = re.sub(pattern, replacement, verifier_src)
        VERIFIER_FILE.write_text(verifier_src, encoding="utf-8")
        log(f"Embedded RSA public key into {VERIFIER_FILE.name}")
        return True
    else:
        error("Could not find VERIFICATION_PUBLIC_KEY_PEM in entitlement_verifier.py")
        return False


# ── Step 3: Generate Integrity Manifest ──────────────────────────────────────

def generate_integrity_manifest() -> dict:
    """Generate SHA256 hashes for critical modules."""
    from engine.security.binary_integrity import BinaryIntegrityChecker
    hashes = BinaryIntegrityChecker.generate_manifest(ROOT)
    log(f"Integrity manifest: {len(hashes)} modules hashed.")
    return hashes


# ── Step 4: Build Metadata ───────────────────────────────────────────────────

def stamp_build_metadata(version: str, build_number: int) -> None:
    """Write build_info.json."""
    info = {
        "app_version": version,
        "build_number": build_number,
        "build_date": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        "protocol_version": "1.0.0",
        "plugin_sdk_version": "1.0.0",
        "environment": "PRODUCTION",
    }
    out = CONFIG_DIR / "build_info.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(info, indent=2), encoding="utf-8")
    log(f"Build metadata: v{version} build {build_number}")


# ── Step 5: Generate Windows Version Info ────────────────────────────────────

def generate_version_info(version: str) -> None:
    """Generate file_version_info.txt for Windows EXE properties."""
    numeric_parts = re.findall(r"\d+", version)
    while len(numeric_parts) < 4:
        numeric_parts.append("0")
    v = tuple(int(p) for p in numeric_parts[:4])

    content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={v},
    prodvers={v},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [
          StringStruct(u'CompanyName', u'Anees Chaudhary'),
          StringStruct(u'FileDescription', u'CHARLIE AI Desktop Assistant'),
          StringStruct(u'FileVersion', u'{version}'),
          StringStruct(u'InternalName', u'CHARLIE'),
          StringStruct(u'LegalCopyright', u'Copyright (C) 2026 Anees Chaudhary. All rights reserved.'),
          StringStruct(u'OriginalFilename', u'CHARLIE.exe'),
          StringStruct(u'ProductName', u'CHARLIE'),
          StringStruct(u'ProductVersion', u'{version}'),
        ],
      ),
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])]),
  ],
)
"""
    out = ROOT / "file_version_info.txt"
    out.write_text(content, encoding="utf-8")
    log(f"Version info generated for {version}")


# ── Step 6: Run PyInstaller ──────────────────────────────────────────────────

def run_pyinstaller() -> bool:
    """Execute PyInstaller with CHARLIE.spec."""
    cmd = [sys.executable, "-m", "PyInstaller", str(ROOT / "CHARLIE.spec"), "--clean", "--noconfirm"]
    log(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    return result.returncode == 0


# ── Step 7: Post-build Validation ────────────────────────────────────────────

def validate_dist() -> tuple:
    """Validate dist/ directory. Returns (ok, issues)."""
    issues = []

    if not DIST_APP.exists():
        issues.append("dist/CHARLIE directory not found.")
        return False, issues

    # Check for leaked source files. Action/plugin modules are intentionally
    # file-backed so the runtime can discover their TOOL manifests, while cv2
    # ships a few Python bootstrap files as vendor data. No other source is
    # permitted in the distribution.
    allowed_source_roots = (
        Path("_internal/actions"),
        Path("_internal/plugins"),
        Path("_internal/cv2"),
    )
    py_files = list(DIST_APP.rglob("*.py"))
    for f in py_files:
        rel = f.relative_to(DIST_APP)
        if f.name == "__init__.py" or any(
            rel == root or root in rel.parents for root in allowed_source_roots
        ):
            continue
        issues.append(f"Source file in dist: {rel}")

    # Scan dist for secrets
    secret_findings = scan_for_secrets(DIST_APP, "dist")
    issues.extend(secret_findings)

    # Check critical files NOT in dist
    banned_in_dist = [
        "config/api_keys.json",
        "licensing_server",
        "admin_panel",
        "tests",
        ".env",
        ".git",
        "requirements.txt",
        "entitlement_signing.pem",
        "credentials.dat",
        "memory/rag_store.sqlite3",
    ]
    for banned in banned_in_dist:
        check_path = DIST_APP / banned
        if check_path.exists():
            issues.append(f"BANNED file/dir in dist: {banned}")

    ok = len(issues) == 0
    return ok, issues


# ── Step 8: Inno Setup Compilation ───────────────────────────────────────────

def compile_installer(version: str = "1.2.4", build_number: int = 109) -> bool:
    """Run Inno Setup compiler if available and organize release artifacts."""
    iss_path = ROOT / "installer.iss"
    if not iss_path.exists():
        error("installer.iss not found.")
        return False

    iscc_paths = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        "iscc",
    ]

    output_name = f"Charlie-AI-Desktop-{version}-Setup"
    iscc_args = [
        f"/DAppVersion={version}",
        f"/DAppNumericVersion={version}.{build_number}",
        f"/DOutputBaseFilename={output_name}",
        str(iss_path),
    ]

    for iscc in iscc_paths:
        try:
            result = subprocess.run([iscc] + iscc_args, cwd=str(ROOT), capture_output=True, text=True)
            if result.returncode == 0:
                log("Inno Setup compilation successful.")
                
                # Locate generated setup file
                candidates = [
                    ROOT / "release" / f"{output_name}.exe",
                    DIST_DIR / f"{output_name}.exe",
                    DIST_DIR / f"CHARLIE-Setup-{version}.exe",
                    DIST_DIR / "CHARLIE-Setup.exe",
                ]
                setup_exe = None
                for c in candidates:
                    if c.exists():
                        setup_exe = c
                        break

                if setup_exe and setup_exe.exists():
                    size_mb = setup_exe.stat().st_size / (1024 * 1024)
                    log(f"Installer: {setup_exe} ({size_mb:.1f} MB)")
                    
                    # Compute SHA-256
                    hasher = hashlib.sha256()
                    with open(setup_exe, "rb") as f:
                        while chunk := f.read(65536):
                            hasher.update(chunk)
                    sha256 = hasher.hexdigest()
                    log(f"SHA-256:   {sha256}")

                    # Organize into release/
                    rel_dir = ROOT / "release"
                    rel_dir.mkdir(parents=True, exist_ok=True)
                    rel_target = rel_dir / f"{output_name}.exe"
                    if rel_target.resolve() != setup_exe.resolve():
                        shutil.copy2(setup_exe, rel_target)
                        setup_exe = rel_target

                    # Write release/SHA256.txt
                    sha_file = rel_dir / "SHA256.txt"
                    sha_file.write_text(f"{sha256} *{output_name}.exe\n", encoding="utf-8")
                    log(f"Release SHA256 written to: {sha_file}")

                    # Update release_manifest.json
                    manifest_file = rel_dir / "release_manifest.json"
                    if manifest_file.exists():
                        try:
                            m_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                            m_data["version"] = version
                            m_data["build_number"] = build_number
                            m_data["installer_filename"] = f"{output_name}.exe"
                            m_data["sha256"] = sha256
                            m_data["installer_size_bytes"] = setup_exe.stat().st_size
                            m_data["installer_size_mb"] = round(setup_exe.stat().st_size / (1024 * 1024), 2)
                            manifest_file.write_text(json.dumps(m_data, indent=2) + "\n", encoding="utf-8")
                            log(f"release_manifest.json updated with SHA-256: {sha256}")
                        except Exception as e:
                            log(f"Warning: could not update release_manifest.json: {e}")

                    # Update update.json
                    update_file = rel_dir / "update.json"
                    if update_file.exists():
                        try:
                            u_data = json.loads(update_file.read_text(encoding="utf-8"))
                            u_data["version"] = version
                            u_data["build_number"] = build_number
                            u_data["installer"] = f"{output_name}.exe"
                            u_data["download_url"] = f"https://github.com/cbasheer74-gif/charlie-ai-assistant/releases/download/v{version}/{output_name}.exe"
                            u_data["sha256"] = sha256
                            update_file.write_text(json.dumps(u_data, indent=2) + "\n", encoding="utf-8")
                            log(f"update.json updated with SHA-256: {sha256}")
                        except Exception as e:
                            log(f"Warning: could not update update.json: {e}")

                    # Also ensure standard alias in landing_page/downloads and dist
                    alias_web = ROOT / "landing_page" / "downloads" / "CHARLIE-Setup.exe"
                    alias_web.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(setup_exe, alias_web)
                    
                    alias_dist = DIST_DIR / "CHARLIE-Setup.exe"
                    if alias_dist != setup_exe:
                        shutil.copy2(setup_exe, alias_dist)
                return True
            else:
                error(f"ISCC failed: {result.stderr}")
        except FileNotFoundError:
            continue

    error("Inno Setup compiler (ISCC.exe) not found. Install Inno Setup 6.")
    return False


def sign_binary(target_path: Path) -> bool:
    """Signs executable with signtool if SIGNTOOL_PATH and CERT_PATH env vars exist."""
    signtool = os.environ.get("SIGNTOOL_PATH", "signtool.exe")
    cert_path = os.environ.get("CODE_SIGN_CERT")
    cert_pass = os.environ.get("CODE_SIGN_PASS")
    timestamp_url = os.environ.get("TIMESTAMP_SERVER", "http://timestamp.digicert.com")

    if not cert_path or not Path(cert_path).exists():
        log(f"Code-signing skipped for {target_path.name} (CODE_SIGN_CERT not set).")
        return True

    cmd = [
        signtool, "sign",
        "/f", cert_path,
        "/tr", timestamp_url,
        "/td", "sha256",
        "/fd", "sha256",
    ]
    if cert_pass:
        cmd.extend(["/p", cert_pass])
    cmd.append(str(target_path))

    try:
        log(f"Signing {target_path.name} with Authenticode SHA-256...")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            log(f"Code-signing SUCCESS for {target_path.name}")
            return True
        else:
            error(f"Code-signing failed: {res.stderr}")
            return False
    except FileNotFoundError:
        log(f"signtool not found on PATH. Executable left unsigned.")
        return True


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    try:
        from config.version import APP_VERSION as DEFAULT_APP_VERSION, BUILD_NUMBER as DEFAULT_BUILD_NUMBER
    except Exception:
        DEFAULT_APP_VERSION = "1.2.4"
        DEFAULT_BUILD_NUMBER = 109

    parser = argparse.ArgumentParser(description="CHARLIE Production Build")
    parser.add_argument("--version", default=DEFAULT_APP_VERSION, help="App version string")
    parser.add_argument("--build-number", type=int, default=DEFAULT_BUILD_NUMBER, help="Build number")
    parser.add_argument("--skip-installer", action="store_true", help="Skip Inno Setup compilation")
    parser.add_argument("--skip-pyinstaller", action="store_true", help="Skip PyInstaller (manifest/validation only)")
    args = parser.parse_args()

    log("=" * 60)
    log("CHARLIE PRODUCTION BUILD")
    log("=" * 60)

    # Step 1: Pre-build secret scan
    log("\n[1/7] Pre-build secret scan...")
    findings = scan_for_secrets(ROOT, "source")
    if findings:
        error("SECRETS DETECTED IN SOURCE:")
        for f in findings:
            error(f"  {f}")
        error("Remove secrets before building. Build ABORTED.")
        sys.exit(1)
    log("No secrets detected. [OK]")

    # Step 2: Embed public key
    log("\n[2/7] Embedding RSA public key...")
    if not embed_public_key():
        error("Public key embedding failed. Build ABORTED.")
        sys.exit(1)
    log("Public key embedded. [OK]")

    # Step 3: Generate integrity manifest
    log("\n[3/7] Generating integrity manifest...")
    sys.path.insert(0, str(ROOT))
    generate_integrity_manifest()
    log("Integrity manifest generated. [OK]")

    # Step 4: Build metadata
    log("\n[4/7] Stamping build metadata...")
    stamp_build_metadata(args.version, args.build_number)
    generate_version_info(args.version)
    log("Build metadata stamped. [OK]")

    if not args.skip_pyinstaller:
        # Step 5: PyInstaller
        log("\n[5/7] Running PyInstaller...")
        if not run_pyinstaller():
            error("PyInstaller build FAILED.")
            sys.exit(1)
        log("PyInstaller build complete. [OK]")

        # Step 6: Post-build validation
        log("\n[6/7] Post-build validation...")
        ok, issues = validate_dist()
        if not ok:
            error("POST-BUILD VALIDATION FAILED:")
            for issue in issues:
                error(f"  [FAIL] {issue}")
            error("Fix issues before distribution.")
            sys.exit(1)
        log("Post-build validation passed. [OK]")
    else:
        log("\n[5/7] Skipping PyInstaller (--skip-pyinstaller)")
        log("[6/7] Skipping post-build validation")

    # Step 7: Inno Setup
    if not args.skip_installer and not args.skip_pyinstaller:
        log("\n[7/7] Compiling installer...")
        compile_installer(args.version, args.build_number)
    elif not args.skip_installer and args.skip_pyinstaller:
        log("\n[7/7] Compiling installer from existing dist...")
        compile_installer(args.version, args.build_number)
    else:
        log("\n[7/7] Skipping installer compilation")

    log("\n" + "=" * 60)
    log("BUILD COMPLETE")
    log("=" * 60)
    if DIST_APP.exists():
        log(f"  App:       {DIST_APP}")
    setup = DIST_DIR / f"CHARLIE-Setup-{args.version}.exe"
    if not setup.exists():
        setup = DIST_DIR / "CHARLIE-Setup.exe"
    if setup.exists():
        log(f"  Installer: {setup}")
    log(f"  Version:   {args.version}")
    log(f"  Build:     {args.build_number}")


if __name__ == "__main__":
    main()
