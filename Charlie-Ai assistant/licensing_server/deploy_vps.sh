#!/usr/bin/env bash
# ==============================================================================
# CHARLIE Licensing Server — 1-Click VPS Deployment Script (Ubuntu / Debian)
# Usage:
#   chmod +x deploy_vps.sh
#   sudo ./deploy_vps.sh
# ==============================================================================

set -euo pipefail

echo "=================================================="
echo " Deploying CHARLIE Licensing Server on VPS"
echo "=================================================="

# 1. Update and install prerequisites
apt-get update -y
apt-get install -y python3 python3-pip python3-venv uvicorn curl git

APP_DIR="/opt/charlie-licensing"
mkdir -p "$APP_DIR"
cp -r . "$APP_DIR/"
cd "$APP_DIR"

# 2. Setup Python Virtual Environment
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 3. Secure permissions
mkdir -p keys data
chmod 700 keys data
if [ -f "keys/entitlement_signing.pem" ]; then
    chmod 600 keys/entitlement_signing.pem
fi
if [ -f ".env.production" ]; then
    chmod 600 .env.production
fi

# 4. Install and enable systemd service
cp charlie-licensing.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable charlie-licensing
systemctl restart charlie-licensing

echo "=================================================="
echo " CHARLIE Licensing Server Started Successfully!"
echo " Status: sudo systemctl status charlie-licensing"
echo " Logs:   sudo journalctl -u charlie-licensing -f"
echo " Port:   8400"
echo "=================================================="
