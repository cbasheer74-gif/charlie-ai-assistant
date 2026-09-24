"""
licensing_server/services/admin_service.py — Commercial Admin Dashboard & Control Operations.

Provides authoritative metrics, revenue analytics, user administration, device reset,
remote license revocation, and audit trails. Strictly zero backdoors or master passwords.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from licensing_server.database import (
    AuditLogDB,
    DeviceDB,
    DeviceStatusEnum,
    LicenseEventDB,
    PaymentDB,
    PlanTier,
    SubscriptionDB,
    SubscriptionStatus,
    SupportTicketDB,
    TransferEventDB,
    UsageEventDB,
    UserDB,
    _utcnow,
)
from licensing_server.services.entitlement_signer import EntitlementSigner

signer = EntitlementSigner()

# Standard monthly plan prices in INR for MRR estimation
PLAN_MONTHLY_PRICES = {
    PlanTier.STARTER.value: 0,
    PlanTier.BASIC.value: 99,
    PlanTier.PREMIUM.value: 199,
    PlanTier.ADVANCED.value: 299,
    PlanTier.PRO.value: 299,
    PlanTier.PRO_PLUS.value: 599,
    PlanTier.ANNUAL_PRO.value: 250,  # Effective monthly contribution (₹2,999/12 ≈ ₹250)
    "PREMIUM": 199,
    "ADVANCED": 299,
    PlanTier.LIFETIME.value: 0,  # One-time, not recurring MRR
}


class AdminService:
    """Core administrative service layer."""

    @staticmethod
    def _record_audit(
        db: Session,
        actor_id: str,
        action: str,
        target_user_id: Optional[str] = None,
        target_device_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        log = AuditLogDB(
            id=f"aud_{uuid.uuid4().hex[:16]}",
            actor_id=actor_id,
            action=action,
            target_user_id=target_user_id,
            target_device_id=target_device_id,
            details_json=json.dumps(details or {}),
            timestamp=_utcnow(),
        )
        db.add(log)
        db.commit()

    def get_overview_metrics(self, db: Session) -> Dict[str, Any]:
        """Compute top-level admin KPI metrics and commercial financials."""
        now = _utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # 1. User counts
        total_users = db.query(func.count(UserDB.id)).scalar() or 0
        new_users_month = db.query(func.count(UserDB.id)).filter(UserDB.created_at >= month_start).scalar() or 0

        # Tier breakdown
        tier_counts = {tier.value: 0 for tier in PlanTier}
        tier_query = (
            db.query(SubscriptionDB.plan, func.count(SubscriptionDB.id))
            .group_by(SubscriptionDB.plan)
            .all()
        )
        for plan_val, count in tier_query:
            if plan_val in tier_counts:
                tier_counts[plan_val] = count

        # Active subscriptions
        active_sub_statuses = [
            SubscriptionStatus.ACTIVE.value,
            SubscriptionStatus.LIFETIME_ACTIVE.value,
            SubscriptionStatus.GRACE_PERIOD.value,
        ]
        active_subscriptions = (
            db.query(func.count(SubscriptionDB.id))
            .filter(SubscriptionDB.status.in_(active_sub_statuses))
            .scalar()
            or 0
        )

        expired_or_cancelled = (
            db.query(func.count(SubscriptionDB.id))
            .filter(SubscriptionDB.status.in_([SubscriptionStatus.EXPIRED.value, SubscriptionStatus.CANCELLED.value]))
            .scalar()
            or 0
        )

        # Devices
        active_devices = (
            db.query(func.count(DeviceDB.id))
            .filter(DeviceDB.status == DeviceStatusEnum.ACTIVE.value)
            .scalar()
            or 0
        )
        total_transfers = db.query(func.count(TransferEventDB.id)).scalar() or 0

        # Suspicious activations (e.g., tamper events, or multiple fast transfers)
        suspicious_activations = (
            db.query(func.count(LicenseEventDB.id))
            .filter(LicenseEventDB.event_type == "TAMPER_DETECTED")
            .scalar()
            or 0
        )

        # 2. Revenue calculation (amounts stored in paise -> divide by 100)
        captured_statuses = ["CAPTURED", "VERIFIED", "SUCCESS"]
        
        today_rev_paise = (
            db.query(func.sum(PaymentDB.amount_paise))
            .filter(PaymentDB.status.in_(captured_statuses), PaymentDB.created_at >= today_start)
            .scalar()
            or 0
        )
        monthly_rev_paise = (
            db.query(func.sum(PaymentDB.amount_paise))
            .filter(PaymentDB.status.in_(captured_statuses), PaymentDB.created_at >= month_start)
            .scalar()
            or 0
        )
        lifetime_sales_paise = (
            db.query(func.sum(PaymentDB.amount_paise))
            .filter(PaymentDB.status.in_(captured_statuses))
            .scalar()
            or 0
        )

        today_revenue = round(today_rev_paise / 100.0, 2)
        monthly_revenue = round(monthly_rev_paise / 100.0, 2)
        lifetime_sales = round(lifetime_sales_paise / 100.0, 2)

        # Failed payments
        failed_payments = (
            db.query(func.count(PaymentDB.id))
            .filter(PaymentDB.status.in_(["FAILED", "DECLINED", "CANCELLED"]))
            .scalar()
            or 0
        )

        # MRR calculation based on current active monthly subscriptions
        active_subs = (
            db.query(SubscriptionDB.plan)
            .filter(SubscriptionDB.status.in_([SubscriptionStatus.ACTIVE.value, SubscriptionStatus.GRACE_PERIOD.value]))
            .all()
        )
        mrr = sum(PLAN_MONTHLY_PRICES.get(sub.plan, 0) for sub in active_subs)

        # Churn rate: cancelled / total historical paid
        paid_plans = [PlanTier.BASIC.value, PlanTier.PREMIUM.value, PlanTier.ADVANCED.value, PlanTier.LIFETIME.value]
        total_paid_users = (
            db.query(func.count(SubscriptionDB.id))
            .filter(SubscriptionDB.plan.in_(paid_plans))
            .scalar()
            or 0
        )
        cancelled_paid = (
            db.query(func.count(SubscriptionDB.id))
            .filter(SubscriptionDB.status == SubscriptionStatus.CANCELLED.value)
            .scalar()
            or 0
        )
        churn_rate = round((cancelled_paid / total_paid_users * 100.0) if total_paid_users > 0 else 0.0, 1)

        # Conversion Starter -> Paid
        starter_users = tier_counts.get(PlanTier.STARTER.value, 0)
        conversion_rate = round(
            (total_paid_users / total_users * 100.0) if total_users > 0 else 0.0, 1
        )

        # Open support tickets
        open_tickets = (
            db.query(func.count(SupportTicketDB.id))
            .filter(SupportTicketDB.status.in_(["OPEN", "IN_PROGRESS"]))
            .scalar()
            or 0
        )

        # AI cost and credits
        total_ai_cost = float(db.query(func.sum(UsageEventDB.estimated_provider_cost)).scalar() or 0.0)
        total_credits_used = int(db.query(func.sum(UsageEventDB.credits_used)).scalar() or 0)
        razorpay_fee_est = round(monthly_revenue * 0.02, 2)
        gross_profit_est = round(monthly_revenue - total_ai_cost - razorpay_fee_est, 2)
        gross_margin_pct = round((gross_profit_est / monthly_revenue * 100), 1) if monthly_revenue > 0 else 0.0

        return {
            "total_users": total_users,
            "new_users_month": new_users_month,
            "tier_counts": tier_counts,
            "active_subscriptions": active_subscriptions,
            "expired_or_cancelled": expired_or_cancelled,
            "active_devices": active_devices,
            "total_transfers": total_transfers,
            "suspicious_activations": suspicious_activations,
            "failed_payments": failed_payments,
            "open_tickets": open_tickets,
            "revenue": {
                "today": today_revenue,
                "monthly": monthly_revenue,
                "lifetime": lifetime_sales,
                "mrr": mrr,
                "currency": "INR",
                "symbol": "₹",
            },
            "profitability": {
                "ai_api_cost_inr": round(total_ai_cost, 2),
                "razorpay_fees_inr": razorpay_fee_est,
                "estimated_gross_profit_inr": gross_profit_est,
                "gross_margin_pct": gross_margin_pct,
                "total_credits_used": total_credits_used,
            },
            "analytics": {
                "churn_rate_pct": churn_rate,
                "conversion_rate_pct": conversion_rate,
            },
        }

    def search_users(
        self,
        db: Session,
        query: str = "",
        plan: str = "",
        status_filter: str = "",
        page: int = 1,
        page_size: int = 25,
    ) -> Dict[str, Any]:
        """Search and filter registered users with pagination."""
        q = db.query(UserDB).join(SubscriptionDB, UserDB.id == SubscriptionDB.user_id, isouter=True)

        if query:
            clean_q = f"%{query.strip().lower()}%"
            q = q.filter(
                or_(
                    UserDB.email.ilike(clean_q),
                    UserDB.display_name.ilike(clean_q),
                    UserDB.id.ilike(clean_q),
                )
            )

        if plan:
            q = q.filter(SubscriptionDB.plan == plan.upper())

        if status_filter:
            q = q.filter(UserDB.account_status == status_filter.upper())

        total = q.count()
        users = (
            q.order_by(UserDB.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        results = []
        for u in users:
            sub = u.subscription
            results.append({
                "id": u.id,
                "email": u.email,
                "display_name": u.display_name,
                "role": getattr(u, "role", "USER"),
                "account_status": u.account_status,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "last_login": u.last_login.isoformat() if u.last_login else None,
                "plan": sub.plan if sub else "STARTER",
                "subscription_status": sub.status if sub else "FREE",
                "active_device_id": sub.active_device_id if sub else None,
            })

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "users": results,
        }

    def get_user_detail(self, db: Session, user_id: str) -> Optional[Dict[str, Any]]:
        """Fetch comprehensive details for an individual user without exposing passwords."""
        user = db.query(UserDB).filter(UserDB.id == user_id).first()
        if not user:
            return None

        sub = user.subscription
        devices = db.query(DeviceDB).filter(DeviceDB.user_id == user.id).all()
        payments = (
            db.query(PaymentDB)
            .filter(PaymentDB.user_id == user.id)
            .order_by(PaymentDB.created_at.desc())
            .all()
        )
        tickets = (
            db.query(SupportTicketDB)
            .filter(SupportTicketDB.user_id == user.id)
            .order_by(SupportTicketDB.created_at.desc())
            .all()
        )
        audit_history = (
            db.query(AuditLogDB)
            .filter(AuditLogDB.target_user_id == user.id)
            .order_by(AuditLogDB.timestamp.desc())
            .limit(20)
            .all()
        )

        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "role": getattr(user, "role", "USER"),
                "account_status": user.account_status,
                "session_version": getattr(user, "session_version", 1),
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login": user.last_login.isoformat() if user.last_login else None,
            },
            "subscription": {
                "id": sub.id if sub else None,
                "plan": sub.plan if sub else "STARTER",
                "status": sub.status if sub else "FREE",
                "active_device_id": sub.active_device_id if sub else None,
                "started_at": sub.started_at.isoformat() if sub and sub.started_at else None,
                "expires_at": sub.expires_at.isoformat() if sub and sub.expires_at else None,
                "payment_reference": sub.payment_reference if sub else None,
            },
            "devices": [
                {
                    "id": d.id,
                    "device_name": d.device_name,
                    "os_type": d.os_type,
                    "app_version": d.app_version,
                    "status": d.status,
                    "activated_at": d.activated_at.isoformat() if d.activated_at else None,
                    "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                    "fingerprint_prefix": d.fingerprint_hash[:16] + "...",
                }
                for d in devices
            ],
            "payments": [
                {
                    "id": p.id,
                    "provider": p.provider,
                    "order_id": p.order_id,
                    "payment_id": p.payment_id,
                    "amount_inr": p.amount_paise / 100.0,
                    "plan": p.plan,
                    "status": p.status,
                    "verified_at": p.verified_at.isoformat() if p.verified_at else None,
                }
                for p in payments
            ],
            "tickets": [
                {
                    "id": t.id,
                    "ticket_number": t.ticket_number,
                    "subject": t.subject,
                    "status": t.status,
                    "priority": t.priority,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in tickets
            ],
            "audit_trail": [
                {
                    "action": a.action,
                    "actor_id": a.actor_id,
                    "timestamp": a.timestamp.isoformat() if a.timestamp else None,
                    "details": json.loads(a.details_json or "{}"),
                }
                for a in audit_history
            ],
        }

    def suspend_user(self, db: Session, admin_id: str, user_id: str, reason: str = "") -> Tuple[bool, str]:
        """Suspend a user account and invalidate their active sessions."""
        user = db.query(UserDB).filter(UserDB.id == user_id).first()
        if not user:
            return False, "User not found."

        user.account_status = "SUSPENDED"
        user.session_version = (getattr(user, "session_version", 1) or 1) + 1

        # Also deactivate subscription active device
        sub = user.subscription
        if sub and sub.active_device_id:
            dev = db.query(DeviceDB).filter(DeviceDB.id == sub.active_device_id).first()
            if dev:
                dev.status = DeviceStatusEnum.REVOKED.value
            sub.active_device_id = None

        db.commit()
        self._record_audit(
            db, actor_id=admin_id, action="SUSPEND_USER", target_user_id=user.id, details={"reason": reason}
        )
        return True, "User account suspended and active sessions revoked."

    def reactivate_user(self, db: Session, admin_id: str, user_id: str) -> Tuple[bool, str]:
        """Reactivate a suspended user account."""
        user = db.query(UserDB).filter(UserDB.id == user_id).first()
        if not user:
            return False, "User not found."

        user.account_status = "ACTIVE"
        db.commit()
        self._record_audit(db, actor_id=admin_id, action="REACTIVATE_USER", target_user_id=user.id)
        return True, "User account reactivated."

    def reset_device_activation(self, db: Session, admin_id: str, user_id: str) -> Tuple[bool, str]:
        """Admin unlinks active device for a customer so they can activate on a new machine."""
        user = db.query(UserDB).filter(UserDB.id == user_id).first()
        if not user:
            return False, "User not found."

        sub = user.subscription
        if not sub:
            return False, "Subscription not found."

        prev_device_id = sub.active_device_id
        if prev_device_id:
            dev = db.query(DeviceDB).filter(DeviceDB.id == prev_device_id).first()
            if dev:
                dev.status = DeviceStatusEnum.INACTIVE.value
            sub.active_device_id = None
            db.commit()

        self._record_audit(
            db,
            actor_id=admin_id,
            action="RESET_DEVICE_ACTIVATION",
            target_user_id=user.id,
            target_device_id=prev_device_id,
        )
        return True, f"Device activation cleared. User can now bind a new PC."

    def grant_entitlement(
        self,
        db: Session,
        admin_id: str,
        user_id: str,
        plan: str,
        days: int = 30,
        reason: str = "Admin manual entitlement",
    ) -> Tuple[bool, str]:
        """Grant temporary or promotional plan entitlement to user."""
        user = db.query(UserDB).filter(UserDB.id == user_id).first()
        if not user:
            return False, "User not found."

        sub = user.subscription
        if not sub:
            sub = SubscriptionDB(
                id=f"sub_{uuid.uuid4().hex[:16]}",
                user_id=user.id,
                plan=PlanTier.STARTER.value,
                status=SubscriptionStatus.FREE.value,
            )
            db.add(sub)

        target_plan = plan.upper()
        if target_plan not in [p.value for p in PlanTier]:
            return False, f"Invalid plan: {plan}"

        sub.plan = target_plan
        sub.status = (
            SubscriptionStatus.LIFETIME_ACTIVE.value
            if target_plan == PlanTier.LIFETIME.value
            else SubscriptionStatus.ACTIVE.value
        )
        sub.started_at = _utcnow()
        if target_plan == PlanTier.LIFETIME.value:
            sub.expires_at = None
        else:
            sub.expires_at = _utcnow() + timedelta(days=days)

        db.commit()
        self._record_audit(
            db,
            actor_id=admin_id,
            action="GRANT_ENTITLEMENT",
            target_user_id=user.id,
            details={"plan": target_plan, "days": days, "reason": reason},
        )
        return True, f"Granted {target_plan} plan to {user.email} for {days} days."

    def revoke_device_license(
        self, db: Session, admin_id: str, device_id: str, reason: str = "Suspicious activity"
    ) -> Tuple[bool, str]:
        """Remote kill-switch: Immediately revoke device license. Propagates on next revalidation."""
        dev = db.query(DeviceDB).filter(DeviceDB.id == device_id).first()
        if not dev:
            return False, "Device not found."

        dev.status = DeviceStatusEnum.REVOKED.value

        # Unlink from subscription
        sub = db.query(SubscriptionDB).filter(SubscriptionDB.active_device_id == device_id).first()
        if sub:
            sub.active_device_id = None

        db.commit()
        self._record_audit(
            db,
            actor_id=admin_id,
            action="REVOKE_DEVICE_LICENSE",
            target_user_id=dev.user_id,
            target_device_id=dev.id,
            details={"reason": reason},
        )
        return True, f"Device {device_id} revoked. Next client refresh will lock paid features."

    def get_audit_logs(
        self,
        db: Session,
        user_id: str = "",
        actor_id: str = "",
        action: str = "",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Retrieve administrative audit logs with optional filters."""
        q = db.query(AuditLogDB)
        if user_id:
            q = q.filter(AuditLogDB.target_user_id == user_id)
        if actor_id:
            q = q.filter(AuditLogDB.actor_id == actor_id)
        if action:
            q = q.filter(AuditLogDB.action == action.upper())

        logs = q.order_by(AuditLogDB.timestamp.desc()).limit(limit).all()
        return [
            {
                "id": l.id,
                "actor_id": l.actor_id,
                "action": l.action,
                "target_user_id": l.target_user_id,
                "target_device_id": l.target_device_id,
                "details": json.loads(l.details_json or "{}"),
                "timestamp": l.timestamp.isoformat() if l.timestamp else None,
            }
            for l in logs
        ]

    def get_security_monitoring(self, db: Session) -> Dict[str, Any]:
        """Aggregate security alerts: tamper attempts, suspicious devices, failed logins."""
        tamper_events = (
            db.query(LicenseEventDB)
            .filter(LicenseEventDB.event_type.in_(["TAMPER_DETECTED", "SIGNATURE_INVALID", "DEVICE_MISMATCH"]))
            .order_by(LicenseEventDB.timestamp.desc())
            .limit(20)
            .all()
        )
        suspicious_devices = (
            db.query(DeviceDB)
            .filter(DeviceDB.security_flag != "NORMAL")
            .limit(20)
            .all()
        )
        failed_payments = (
            db.query(PaymentDB)
            .filter(PaymentDB.status.in_(["FAILED", "DECLINED"]))
            .order_by(PaymentDB.created_at.desc())
            .limit(20)
            .all()
        )
        return {
            "tamper_count": len(tamper_events),
            "suspicious_device_count": len(suspicious_devices),
            "failed_payment_count": len(failed_payments),
            "recent_tamper_events": [
                {
                    "id": e.id,
                    "user_id": e.user_id,
                    "device_id": e.device_id,
                    "event_type": e.event_type,
                    "details": json.loads(e.details_json or "{}"),
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                }
                for e in tamper_events
            ],
            "suspicious_devices": [
                {
                    "id": d.id,
                    "user_id": d.user_id,
                    "name": d.device_name,
                    "security_flag": d.security_flag,
                    "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                }
                for d in suspicious_devices
            ],
        }

    def add_user_internal_note(
        self, db: Session, admin_id: str, user_id: str, note_text: str
    ) -> Tuple[bool, str]:
        """Store private staff note on customer record. Never exposed to customer."""
        user = db.query(UserDB).filter(UserDB.id == user_id).first()
        if not user:
            return False, "User not found."
        existing = user.internal_notes or ""
        timestamp_str = _utcnow().strftime("%Y-%m-%d %H:%M UTC")
        entry = f"[{timestamp_str} by {admin_id}]: {note_text}"
        user.internal_notes = f"{existing}\n{entry}".strip()
        db.commit()
        self._record_audit(db, actor_id=admin_id, action="ADD_USER_NOTE", target_user_id=user.id)
        return True, "Staff note recorded."

    def set_user_tags(
        self, db: Session, admin_id: str, user_id: str, tags: str
    ) -> Tuple[bool, str]:
        """Set customer tags e.g. VIP, Beta Tester, Payment Review."""
        user = db.query(UserDB).filter(UserDB.id == user_id).first()
        if not user:
            return False, "User not found."
        user.tags = tags.strip()
        db.commit()
        self._record_audit(db, actor_id=admin_id, action="UPDATE_USER_TAGS", target_user_id=user.id, details={"tags": tags})
        return True, "Tags updated."

    def export_csv(self, db: Session, entity_type: str = "users") -> str:
        """Export sanitized CSV of users, payments, subscriptions, or support tickets."""
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        if entity_type == "users":
            writer.writerow(["User ID", "Email", "Display Name", "Role", "Status", "Tags", "Created At"])
            users = db.query(UserDB).order_by(UserDB.created_at.desc()).limit(1000).all()
            for u in users:
                writer.writerow([u.id, u.email, u.display_name, getattr(u, "role", "USER"), u.account_status, u.tags or "", u.created_at])
        elif entity_type == "payments":
            writer.writerow(["Payment ID", "User ID", "Order ID", "Plan", "Amount INR", "Status", "Verified At"])
            payments = db.query(PaymentDB).order_by(PaymentDB.created_at.desc()).limit(1000).all()
            for p in payments:
                writer.writerow([p.id, p.user_id, p.order_id, p.plan, p.amount_paise / 100.0, p.status, p.verified_at])
        elif entity_type == "subscriptions":
            writer.writerow(["Sub ID", "User ID", "Plan", "Status", "Active Device", "Expires At"])
            subs = db.query(SubscriptionDB).order_by(SubscriptionDB.started_at.desc()).limit(1000).all()
            for s in subs:
                writer.writerow([s.id, s.user_id, s.plan, s.status, s.active_device_id or "", s.expires_at])
        elif entity_type == "tickets":
            writer.writerow(["Ticket #", "User ID", "Category", "Subject", "Status", "Priority", "Created At"])
            tickets = db.query(SupportTicketDB).order_by(SupportTicketDB.created_at.desc()).limit(1000).all()
            for t in tickets:
                writer.writerow([t.ticket_number, t.user_id, t.category, t.subject, t.status, t.priority, t.created_at])

        return output.getvalue()
