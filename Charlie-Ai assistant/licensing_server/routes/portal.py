"""
licensing_server/routes/portal.py — Customer Account Self-Service Portal & API.

Provides:
1. RESTful Customer Portal API (overview, device deactivation, transfer, subscription cancellation, password change, logout-all).
2. Embedded Cybernetic Dark HUD Customer Account Portal Web Interface (GET /portal).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from licensing_server.config import config
from licensing_server.database import (
    DeviceDB,
    DeviceStatusEnum,
    PaymentDB,
    SubscriptionDB,
    SubscriptionStatus,
    UserDB,
    get_db,
)
from licensing_server.middleware.auth_middleware import get_current_user
from licensing_server.services.auth_service import AuthService

router = APIRouter(prefix="/portal", tags=["Customer Account Portal"])
auth_service = AuthService()


# ── Request / Response Schemas ───────────────────────────────────────────────

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)


class TransferDeviceRequest(BaseModel):
    confirm: bool = Field(default=True)


# ── Portal API Endpoints ─────────────────────────────────────────────────────

@router.get("/api/overview")
def get_portal_overview(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Customer overview: plan details, active bound PC, billing history, installer url."""
    sub = user.subscription
    active_device = None
    if sub and sub.active_device_id:
        dev = db.query(DeviceDB).filter(DeviceDB.id == sub.active_device_id).first()
        if dev:
            active_device = {
                "id": dev.id,
                "name": dev.device_name,
                "os": dev.os_type,
                "version": dev.app_version,
                "status": dev.status,
                "activated_at": dev.activated_at.isoformat() if dev.activated_at else None,
                "last_seen": dev.last_seen.isoformat() if dev.last_seen else None,
            }

    payments = (
        db.query(PaymentDB)
        .filter(PaymentDB.user_id == user.id)
        .order_by(PaymentDB.created_at.desc())
        .limit(10)
        .all()
    )

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "subscription": {
            "plan": sub.plan if sub else "STARTER",
            "status": sub.status if sub else "FREE",
            "expires_at": sub.expires_at.isoformat() if sub and sub.expires_at else None,
            "started_at": sub.started_at.isoformat() if sub and sub.started_at else None,
            "device_limit": sub.device_limit if sub else 1,
        },
        "active_device": active_device,
        "installer": {
            "version": config.LATEST_APP_VERSION,
            "download_url": config.INSTALLER_DOWNLOAD_URL,
            "file_size": "151 MB",
            "os": "Windows 10 / 11 (64-bit)",
        },
        "billing_history": [
            {
                "id": p.id,
                "amount_inr": p.amount_paise / 100.0,
                "plan": p.plan,
                "status": p.status,
                "date": p.created_at.isoformat() if p.created_at else None,
            }
            for p in payments
        ],
    }


@router.post("/api/device/deactivate")
def deactivate_device(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Customer unbinds their currently active PC."""
    sub = user.subscription
    if not sub or not sub.active_device_id:
        return {"status": "ok", "message": "No device currently bound."}

    dev = db.query(DeviceDB).filter(DeviceDB.id == sub.active_device_id).first()
    if dev:
        dev.status = DeviceStatusEnum.INACTIVE.value
    sub.active_device_id = None
    db.commit()

    return {"status": "ok", "message": "Device deactivated. License slot is now free."}


@router.post("/api/device/transfer")
def transfer_device(
    req: TransferDeviceRequest,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Prepare license for transfer to another PC."""
    sub = user.subscription
    if not sub:
        raise HTTPException(status_code=400, detail="Subscription not found.")

    if sub.active_device_id:
        dev = db.query(DeviceDB).filter(DeviceDB.id == sub.active_device_id).first()
        if dev:
            dev.status = DeviceStatusEnum.INACTIVE.value
        sub.active_device_id = None
        db.commit()

    return {
        "status": "ok",
        "message": "License cleared for transfer. Log in on your new PC to complete activation.",
    }


@router.post("/api/subscription/cancel")
def cancel_subscription(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel subscription at end of billing cycle."""
    sub = user.subscription
    if not sub or sub.plan == "STARTER":
        raise HTTPException(status_code=400, detail="No active paid subscription to cancel.")

    if sub.plan == "LIFETIME":
        raise HTTPException(status_code=400, detail="Lifetime licenses cannot be cancelled.")

    sub.status = SubscriptionStatus.CANCEL_AT_PERIOD_END.value
    db.commit()
    return {
        "status": "ok",
        "message": "Subscription set to cancel at end of current billing period. Paid features remain active until expiry.",
    }


@router.post("/api/password/change")
def change_password(
    req: ChangePasswordRequest,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change customer password and invalidate all existing sessions."""
    success, msg = auth_service.change_password(
        db, user=user, old_pass=req.current_password, new_pass=req.new_password
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@router.post("/api/logout-all")
def logout_all_devices(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Invalidate all active sessions across all devices."""
    auth_service.invalidate_all_sessions(db, user=user)
    return {"status": "ok", "message": "All sessions logged out successfully."}


# ── Embedded Cybernetic Dark HUD Web UI ──────────────────────────────────────

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def portal_dashboard_ui():
    """Standalone, responsive Cybernetic Dark HUD Customer Account Portal."""
    return HTMLResponse(content=PORTAL_DASHBOARD_HTML, status_code=200)


PORTAL_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>JARVIS Customer Portal — Account & License</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #07090e;
      --panel: #0d1117;
      --card: #121824;
      --border: rgba(0, 229, 255, 0.15);
      --border-bright: rgba(0, 229, 255, 0.4);
      --cyan: #00e5ff;
      --cyan-dim: rgba(0, 229, 255, 0.08);
      --blue: #3b82f6;
      --green: #10b981;
      --amber: #f59e0b;
      --red: #ef4444;
      --text: #f1f5f9;
      --text-dim: #94a3b8;
      --text-muted: #64748b;
      --font-main: 'Space Grotesk', -apple-system, BlinkMacSystemFont, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: var(--font-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      background: rgba(13, 17, 23, 0.85);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
      padding: 1rem 2rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .brand { display: flex; align-items: center; gap: 0.75rem; }
    .brand-badge {
      background: var(--cyan-dim);
      border: 1px solid var(--cyan);
      color: var(--cyan);
      font-family: var(--font-mono);
      font-size: 0.7rem;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      font-weight: 600;
    }
    .brand h1 { font-size: 1.15rem; font-weight: 700; color: #fff; }
    main {
      flex: 1;
      padding: 2rem;
      max-width: 1080px;
      width: 100%;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      gap: 1.75rem;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }
    .card-title {
      font-size: 1rem;
      font-weight: 600;
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.75rem;
    }
    .grid-2 {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 1rem;
    }
    .info-box {
      background: #090d14;
      padding: 0.8rem 1rem;
      border-radius: 8px;
      border: 1px solid rgba(255, 255, 255, 0.05);
    }
    .info-label { font-size: 0.75rem; color: var(--text-muted); font-family: var(--font-mono); text-transform: uppercase; }
    .info-value { font-size: 1.1rem; font-weight: 600; color: #fff; margin-top: 0.25rem; word-break: break-all; }
    .badge {
      display: inline-block;
      padding: 0.2rem 0.6rem;
      border-radius: 4px;
      font-family: var(--font-mono);
      font-size: 0.75rem;
      font-weight: 600;
    }
    .badge-plan { background: rgba(0, 229, 255, 0.2); color: var(--cyan); border: 1px solid var(--cyan); }
    .badge-active { background: rgba(16, 185, 129, 0.15); color: var(--green); border: 1px solid rgba(16, 185, 129, 0.3); }
    .btn {
      background: var(--cyan);
      color: #050b14;
      font-family: var(--font-main);
      font-weight: 600;
      font-size: 0.85rem;
      padding: 0.6rem 1.2rem;
      border-radius: 6px;
      border: none;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      transition: all 0.2s;
    }
    .btn:hover { transform: translateY(-1px); box-shadow: 0 0 14px rgba(0, 229, 255, 0.4); }
    .btn-secondary { background: transparent; color: var(--text-dim); border: 1px solid var(--border); }
    .btn-secondary:hover { color: #fff; border-color: var(--cyan); background: var(--cyan-dim); }
    .btn-danger { background: rgba(239, 68, 68, 0.15); color: var(--red); border: 1px solid rgba(239, 68, 68, 0.3); }
    .btn-danger:hover { background: var(--red); color: #fff; box-shadow: 0 0 14px rgba(239, 68, 68, 0.4); }
    .input-field {
      background: #090d14;
      border: 1px solid var(--border);
      color: #fff;
      font-family: var(--font-main);
      padding: 0.6rem 1rem;
      border-radius: 6px;
      font-size: 0.85rem;
      outline: none;
      width: 100%;
    }
    .input-field:focus { border-color: var(--cyan); }
    .auth-banner {
      background: #0d121c;
      border: 1px solid var(--border);
      padding: 2rem;
      border-radius: 12px;
      text-align: center;
      display: flex;
      flex-direction: column;
      gap: 1rem;
      max-width: 400px;
      margin: 3rem auto;
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <span class="brand-badge">JARVIS PORTAL</span>
      <h1>Customer Account & Licensing</h1>
    </div>
    <div id="authHeader" style="display:none; align-items:center; gap:1rem;">
      <span id="userEmailSpan" style="font-size:0.85rem;color:var(--text-dim);font-family:var(--font-mono);"></span>
      <button class="btn btn-secondary" onclick="logoutUser()">Sign Out</button>
    </div>
  </header>

  <!-- LOGIN CONTAINER (shown if not authenticated) -->
  <div id="loginSection" class="auth-banner">
    <h2 style="font-size:1.25rem;color:#fff;">Sign In to Customer Portal</h2>
    <p style="font-size:0.85rem;color:var(--text-dim);">Manage your subscription, active PC license, and downloads.</p>
    <input type="email" id="loginEmail" class="input-field" placeholder="Email address">
    <input type="password" id="loginPassword" class="input-field" placeholder="Password">
    <button class="btn" onclick="submitLogin()">Sign In</button>
  </div>

  <!-- MAIN PORTAL DASHBOARD (shown if authenticated) -->
  <main id="portalMain" style="display: none;">
    <!-- Plan & Subscription -->
    <div class="card">
      <div class="card-title">
        <span>Subscription & Entitlement</span>
        <span id="planBadge" class="badge badge-plan">STARTER</span>
      </div>
      <div class="grid-2">
        <div class="info-box">
          <div class="info-label">Current Plan Status</div>
          <div class="info-value" id="subStatusVal">FREE</div>
        </div>
        <div class="info-box">
          <div class="info-label">Renewal / Expiry Date</div>
          <div class="info-value" id="expiresVal">Never (Starter)</div>
        </div>
      </div>
      <div style="display:flex;gap:0.75rem;flex-wrap:wrap;margin-top:0.5rem;">
        <button class="btn btn-secondary" onclick="window.location.href='/#pricing'">Upgrade / Change Plan</button>
        <button class="btn btn-danger" id="cancelSubBtn" onclick="cancelSub()">Cancel Subscription</button>
      </div>
    </div>

    <!-- Active Device Management -->
    <div class="card">
      <div class="card-title">
        <span>Active Licensed PC</span>
        <span class="badge badge-active" id="deviceStatusBadge">1 PC Bound</span>
      </div>
      <div id="deviceDetailsBox" class="grid-2">
        <div class="info-box">
          <div class="info-label">Device Name & OS</div>
          <div class="info-value" id="deviceNameVal">No active PC bound</div>
        </div>
        <div class="info-box">
          <div class="info-label">Bound Since</div>
          <div class="info-value" id="deviceBoundVal">—</div>
        </div>
      </div>
      <div style="display:flex;gap:0.75rem;flex-wrap:wrap;margin-top:0.5rem;">
        <button class="btn btn-secondary" onclick="deactivateDevice()">Deactivate This PC</button>
        <button class="btn" onclick="transferDevice()">Transfer License to New PC</button>
      </div>
    </div>

    <!-- Installer Download -->
    <div class="card">
      <div class="card-title">
        <span>Official JARVIS Production Installer</span>
        <span style="font-size:0.8rem;color:var(--cyan);font-family:var(--font-mono);">v1.0.0 Verified</span>
      </div>
      <p style="font-size:0.85rem;color:var(--text-dim);">
        Download the standalone production installer for Windows 10 & 11 (64-bit). Includes runtime, AI engine, and full offline verification.
      </p>
      <div>
        <a id="downloadInstallerBtn" href="/downloads/JARVIS-Setup.exe" class="btn" download>
          Download JARVIS-Setup.exe (151 MB)
        </a>
      </div>
    </div>

    <!-- Security & Account -->
    <div class="card">
      <div class="card-title">Security & Device Sessions</div>
      <div class="grid-2">
        <div style="display:flex;flex-direction:column;gap:0.5rem;">
          <label class="info-label">Change Password</label>
          <input type="password" id="oldPassword" class="input-field" placeholder="Current password">
          <input type="password" id="newPassword" class="input-field" placeholder="New password (min 6 chars)">
          <button class="btn btn-secondary" style="align-self:flex-start;" onclick="changePassword()">Update Password</button>
        </div>
        <div style="display:flex;flex-direction:column;gap:0.75rem;justify-content:center;">
          <div>
            <div style="color:#fff;font-weight:600;font-size:0.9rem;">Global Session Sign-Out</div>
            <div style="color:var(--text-muted);font-size:0.8rem;margin-top:0.25rem;">
              Immediately invalidates all login tokens across all web and desktop instances.
            </div>
          </div>
          <button class="btn btn-danger" style="align-self:flex-start;" onclick="logoutAll()">Logout All Devices</button>
        </div>
      </div>
    </div>
  </main>

  <script>
    let token = localStorage.getItem('jarvis_portal_token');

    async function submitLogin() {
      const email = document.getElementById('loginEmail').value.trim();
      const password = document.getElementById('loginPassword').value;
      if (!email || !password) { alert('Email and password required'); return; }

      try {
        const res = await fetch('/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Login failed');
        token = data.access_token;
        localStorage.setItem('jarvis_portal_token', token);
        initPortal();
      } catch (e) {
        alert(e.message);
      }
    }

    async function initPortal() {
      if (!token) {
        document.getElementById('loginSection').style.display = 'flex';
        document.getElementById('portalMain').style.display = 'none';
        document.getElementById('authHeader').style.display = 'none';
        return;
      }

      try {
        const res = await fetch('/portal/api/overview', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (res.status === 401 || res.status === 403) {
          logoutUser();
          return;
        }
        const data = await res.json();
        document.getElementById('loginSection').style.display = 'none';
        document.getElementById('portalMain').style.display = 'flex';
        document.getElementById('authHeader').style.display = 'flex';
        document.getElementById('userEmailSpan').innerText = data.user.email;

        // Plan
        document.getElementById('planBadge').innerText = data.subscription.plan;
        document.getElementById('subStatusVal').innerText = data.subscription.status;
        document.getElementById('expiresVal').innerText = data.subscription.expires_at ? new Date(data.subscription.expires_at).toLocaleDateString() : 'Never (Lifetime / Free)';

        // Device
        if (data.active_device) {
          document.getElementById('deviceStatusBadge').innerText = '1 Active PC Bound';
          document.getElementById('deviceNameVal').innerText = `${data.active_device.name} (${data.active_device.os})`;
          document.getElementById('deviceBoundVal').innerText = new Date(data.active_device.activated_at).toLocaleString();
        } else {
          document.getElementById('deviceStatusBadge').innerText = 'No Active PC';
          document.getElementById('deviceNameVal').innerText = 'No active PC bound';
          document.getElementById('deviceBoundVal').innerText = 'Slot available';
        }
      } catch (e) {
        console.error('Portal init failed:', e);
      }
    }

    async function deactivateDevice() {
      if (!confirm('Deactivate your current PC? You can reactivate anytime by logging into the JARVIS app.')) return;
      try {
        const res = await fetch('/portal/api/device/deactivate', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        });
        const d = await res.json();
        alert(d.message);
        initPortal();
      } catch (e) { alert(e.message); }
    }

    async function transferDevice() {
      if (!confirm('Transfer license to another PC? This unbinds your existing machine.')) return;
      try {
        const res = await fetch('/portal/api/device/transfer', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ confirm: true })
        });
        const d = await res.json();
        alert(d.message);
        initPortal();
      } catch (e) { alert(e.message); }
    }

    async function cancelSub() {
      if (!confirm('Are you sure you want to cancel your subscription?')) return;
      try {
        const res = await fetch('/portal/api/subscription/cancel', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        });
        const d = await res.json();
        alert(d.message);
        initPortal();
      } catch (e) { alert(e.message); }
    }

    async function changePassword() {
      const current_password = document.getElementById('oldPassword').value;
      const new_password = document.getElementById('newPassword').value;
      if (!current_password || !new_password) { alert('Fill both password fields'); return; }
      try {
        const res = await fetch('/portal/api/password/change', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ current_password, new_password })
        });
        const d = await res.json();
        if (!res.ok) throw new Error(d.detail || 'Password change failed');
        alert(d.message);
        logoutUser();
      } catch (e) { alert(e.message); }
    }

    async function logoutAll() {
      if (!confirm('Sign out of all sessions across all devices?')) return;
      try {
        await fetch('/portal/api/logout-all', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        });
        logoutUser();
      } catch (e) { alert(e.message); }
    }

    function logoutUser() {
      localStorage.removeItem('jarvis_portal_token');
      token = null;
      initPortal();
    }

    window.onload = initPortal;
  </script>
</body>
</html>
"""
