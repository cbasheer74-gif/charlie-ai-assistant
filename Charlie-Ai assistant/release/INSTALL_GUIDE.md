# Charlie AI Desktop — Installation Guide (v1.2.4)

Follow these simple steps to install and set up Charlie AI Desktop on Windows.

---

### Step 1: Download Installer
Download the verified setup executable:
- **File:** `Charlie-AI-Desktop-1.2.4-Setup.exe`

### Step 2: Verify Checksum (Optional)
To confirm file integrity, open PowerShell and run:
```powershell
Get-FileHash -Algorithm SHA256 "Charlie-AI-Desktop-1.2.4-Setup.exe"
```
Check against `SHA256.txt` provided in the release.

### Step 3: Run the Installer
1. Double-click `Charlie-AI-Desktop-1.2.4-Setup.exe`.
2. **Windows SmartScreen Prompt:**  
   Because this initial community build is unsigned, Windows may display:
   > "Windows protected your PC — Microsoft Defender SmartScreen prevented an unrecognized app from starting."
   - Click **More info**.
   - Click **Run anyway**.
3. Choose your desired shortcuts (Start Menu shortcut is created by default; desktop icon is optional).
4. Complete the installation. No administrative privileges are required (installs per-user).

### Step 4: First Launch
1. Launch **CHARLIE** from your Start Menu or Desktop.
2. Charlie will initialize local storage in your personal application data folder (`%APPDATA%\CHARLIE`).

### Step 5: Configure Credentials
1. When prompted on the first run, enter your Google Gemini API key into the setup prompt in the Charlie UI.
2. Charlie securely saves your API key into your personal Windows Credential Vault (encrypted with DPAPI).
3. Charlie never stores plaintext API keys in files or requires editing configuration files manually.

---

### Uninstallation & Upgrades
- **To Upgrade:** Simply run any newer installer; existing memory, profiles, and encrypted credentials will be preserved.
- **To Uninstall:** Open Windows Settings → Apps & features → Charlie AI Desktop → Uninstall. Your local memory databases and credentials are kept safe unless you explicitly choose to remove them.
