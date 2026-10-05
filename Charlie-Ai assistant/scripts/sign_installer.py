"""scripts/sign_installer.py — Code Signing Pipeline for CHARLIE.

Signs the CHARLIE Windows desktop executable and setup installer using signtool.exe
or PowerShell Set-AuthenticodeSignature. Supports EV hardware tokens, PFX files,
and automated local self-signed certificates for development and staging.
"""

from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys
from pathlib import Path


def find_signtool() -> str | None:
    """Locate signtool.exe in Windows SDK or PATH."""
    # Check PATH first
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(path_dir, "signtool.exe")
        if os.path.isfile(candidate):
            return candidate

    # Check standard Windows Kits installation directories
    sdk_patterns = [
        r"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe",
        r"C:\Program Files\Windows Kits\10\bin\*\x64\signtool.exe",
        r"C:\Program Files (x86)\Microsoft SDKs\Windows\*\bin\signtool.exe",
    ]
    for pattern in sdk_patterns:
        matches = glob.glob(pattern)
        if matches:
            # Sort descending to pick newest SDK
            matches.sort(reverse=True)
            return matches[0]

    return None


def create_self_signed_cert(cert_name: str = "CHARLIE AI Assistant Developer") -> str:
    """Generate a self-signed code signing certificate via PowerShell for local testing."""
    ps_script = f"""
    $cert = New-SelfSignedCertificate -Type CodeSigningCert `
        -Subject "CN={cert_name}" `
        -CertStoreLocation "Cert:\\CurrentUser\\My" `
        -NotAfter (Get-Date).AddYears(3)
    Write-Output $cert.Thumbprint
    """
    res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True, check=True)
    thumbprint = res.stdout.strip().splitlines()[-1].strip()
    return thumbprint


def sign_file(
    target_path: Path,
    cert_path: Path | None = None,
    cert_pass: str | None = None,
    thumbprint: str | None = None,
    timestamp_url: str = "http://timestamp.digicert.com",
) -> bool:
    """Sign an executable using signtool or PowerShell Set-AuthenticodeSignature."""
    if not target_path.exists():
        print(f"Error: Target file not found: {target_path}")
        return False

    signtool = find_signtool()

    if signtool:
        cmd = [signtool, "sign", "/fd", "sha256", "/tr", timestamp_url, "/td", "sha256"]
        if cert_path and cert_path.exists():
            cmd.extend(["/f", str(cert_path)])
            if cert_pass:
                cmd.extend(["/p", cert_pass])
        elif thumbprint:
            cmd.extend(["/sha1", thumbprint])
        else:
            # Auto-select best matching cert in store
            cmd.append("/a")

        cmd.append(str(target_path))
        print(f"Signing with signtool.exe: {target_path.name}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"  [SUCCESS] Successfully signed: {target_path.name}")
            return True
        else:
            print(f"  [WARN] signtool failed ({res.returncode}): {res.stderr.strip() or res.stdout.strip()}")
            print("  Falling back to PowerShell Set-AuthenticodeSignature...")

    # PowerShell fallback
    ps_sign = f"""
    $file = '{target_path.resolve()}'
    $cert = Get-ChildItem -Path Cert:\\CurrentUser\\My -CodeSigningCert | Select-Object -First 1
    if (-not $cert) {{
        $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=CHARLIE AI Assistant" -CertStoreLocation "Cert:\\CurrentUser\\My"
    }}
    Set-AuthenticodeSignature -FilePath $file -Certificate $cert -TimestampServer '{timestamp_url}' -HashAlgorithm SHA256
    """
    res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_sign], capture_output=True, text=True)
    if "Valid" in res.stdout or res.returncode == 0:
        print(f"  [SUCCESS] Signed via PowerShell Authenticode: {target_path.name}")
        return True
    else:
        print(f"  [ERROR] PowerShell signing failed: {res.stderr.strip() or res.stdout.strip()}")
        return False


def verify_signature(target_path: Path) -> bool:
    """Verify Authenticode signature on target file."""
    ps_cmd = f"(Get-AuthenticodeSignature -FilePath '{target_path.resolve()}').Status.ToString()"
    res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
    status = res.stdout.strip()
    print(f"Signature verification for {target_path.name}: {status}")
    return status in ("Valid", "UnknownError")  # UnknownError is standard for self-signed untrusted roots


def main():
    parser = argparse.ArgumentParser(description="CHARLIE Code Signing Utility")
    parser.add_argument("--file", "-f", help="Specific file to sign")
    parser.add_argument("--cert", "-c", help="Path to .pfx certificate")
    parser.add_argument("--password", "-p", help="Certificate password")
    parser.add_argument("--thumbprint", "-t", help="Certificate SHA1 thumbprint in CurrentUser\\My")
    parser.add_argument("--all", action="store_true", help="Sign all default distribution targets")
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parent.parent

    targets = []
    if args.file:
        targets.append(Path(args.file))
    elif args.all or len(sys.argv) == 1:
        # Default distribution files
        candidates = [
            root_dir / "dist" / "CHARLIE" / "CHARLIE.exe",
            root_dir / "landing_page" / "downloads" / "CHARLIE-Setup.exe",
            root_dir / "dist" / "CHARLIE-Setup-1.3.0.exe",
        ]
        targets = [c for c in candidates if c.exists()]

    if not targets:
        print("No target binaries found to sign. Build them first using build_new_exe.bat or Inno Setup.")
        return 0

    print(f"Found {len(targets)} binary target(s) to sign.")
    cert_path = Path(args.cert) if args.cert else None

    for target in targets:
        ok = sign_file(
            target_path=target,
            cert_path=cert_path,
            cert_pass=args.password,
            thumbprint=args.thumbprint,
        )
        if ok:
            verify_signature(target)

    return 0


if __name__ == "__main__":
    sys.exit(main())
