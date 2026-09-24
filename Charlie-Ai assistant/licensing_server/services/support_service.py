"""
licensing_server/services/support_service.py — Safe diagnostics redactor & ticket management.

All diagnostics automatically strip secrets, API keys, and authorization tokens
before database storage to guarantee user privacy and data security.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from licensing_server.database import (
    DiagnosticRequestDB,
    DiagnosticRequestStatus,
    IncidentDB,
    IncidentSeverity,
    IncidentStatus,
    SupportTicketDB,
    UserDB,
    _utcnow,
)

# Regular expressions for credential and token scrubbing
REDACTION_PATTERNS = [
    # Gemini / Google API Key
    (re.compile(r"AIza[0-9A-Za-z\-_]{20,}"), "[REDACTED_GEMINI_KEY]"),
    # OpenAI / Anthropic Key
    (re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"), "[REDACTED_API_KEY]"),
    # Bearer tokens
    (re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    # JWT format
    (re.compile(r"ey[A-Za-z0-9_-]{15,}\.ey[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_\-]+"), "[REDACTED_JWT]"),
    # Password / secret in json/key-value
    (
        re.compile(
            r'("?(?:password|secret|api_key|access_token|refresh_token|auth_token|client_secret|private_key)"?\s*[:=]\s*["\'])([^"\']+)(["\'])',
            re.IGNORECASE,
        ),
        r"\1[REDACTED]\3",
    ),
    # Database URLs
    (
        re.compile(r"((?:postgres|postgresql|mysql|mongodb|redis|amqp):\/\/[^:\s]+:)([^@\s]+)(@)", re.IGNORECASE),
        r"\1[REDACTED_PASSWORD]\3",
    ),
    # Cookies
    (re.compile(r"(Cookie\s*:\s*)([^\r\n;]+)", re.IGNORECASE), r"\1[REDACTED_COOKIE]"),
    # Private keys (PEM)
    (re.compile(r"-----BEGIN[A-Z\s]+PRIVATE KEY-----[\s\S]*?-----END[A-Z\s]+PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
]

USER_PATH_PATTERN_WIN = re.compile(r"([A-Za-z]:\\Users\\)([^\\]+)(\\)", re.IGNORECASE)
USER_PATH_PATTERN_NIX = re.compile(r"(/home/)([^/]+)(/)", re.IGNORECASE)


class SupportService:
    """Safe support ticket lifecycle and diagnostics sanitization."""

    @staticmethod
    def sanitize_text(text: str) -> str:
        """Sanitize any arbitrary string, scrubbing secrets and personal user paths."""
        if not text:
            return ""
        cleaned = text
        for pattern, replacement in REDACTION_PATTERNS:
            cleaned = pattern.sub(replacement, cleaned)
        cleaned = USER_PATH_PATTERN_WIN.sub(r"\1[USER]\3", cleaned)
        cleaned = USER_PATH_PATTERN_NIX.sub(r"\1[USER]\3", cleaned)
        return cleaned

    @classmethod
    def sanitize_diagnostics(cls, data: Any) -> Any:
        """Recursively sanitize nested dictionaries/lists of telemetry and logs."""
        sensitive_keys = {
            "password", "secret", "api_key", "key", "token", "access_token",
            "refresh_token", "auth", "authorization", "credential", "private_key",
            "cookie", "client_secret",
        }

        if isinstance(data, str):
            return cls.sanitize_text(data)
        elif isinstance(data, dict):
            res = {}
            for k, v in data.items():
                if str(k).lower() in sensitive_keys:
                    res[k] = "[REDACTED]"
                else:
                    res[k] = cls.sanitize_diagnostics(v)
            return res
        elif isinstance(data, list):
            return [cls.sanitize_diagnostics(item) for item in data]
        return data

    def create_ticket(
        self,
        db: Session,
        user: UserDB,
        subject: str,
        message: str,
        category: str = "OTHER",
        error_id: Optional[str] = None,
        app_version: str = "1.0.0",
        os_version: str = "Windows",
        raw_diagnostics: Optional[Dict[str, Any]] = None,
        priority: str = "NORMAL",
    ) -> Tuple[bool, str, Optional[SupportTicketDB]]:
        """Create a new support ticket with automatically sanitized diagnostics."""
        sub = user.subscription
        sub_status = f"{sub.plan} ({sub.status})" if sub else "STARTER (FREE)"

        # Scrub message and diagnostics
        clean_subject = self.sanitize_text(subject)
        clean_message = self.sanitize_text(message)
        clean_diagnostics = self.sanitize_diagnostics(raw_diagnostics or {})

        ticket_num = f"TICK-{uuid.uuid4().hex[:6].upper()}"

        ticket = SupportTicketDB(
            id=f"tkt_{uuid.uuid4().hex[:16]}",
            ticket_number=ticket_num,
            user_id=user.id,
            subject=clean_subject,
            category=category.upper(),
            error_id=error_id,
            app_version=app_version,
            os_version=os_version,
            subscription_status=sub_status,
            diagnostics_json=json.dumps(clean_diagnostics),
            message=clean_message,
            status="OPEN",
            priority=priority.upper(),
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )

        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        return True, "Ticket created successfully.", ticket

    def get_user_tickets(self, db: Session, user_id: str) -> List[Dict[str, Any]]:
        """List tickets belonging to a specific customer."""
        tickets = (
            db.query(SupportTicketDB)
            .filter(SupportTicketDB.user_id == user_id)
            .order_by(SupportTicketDB.created_at.desc())
            .all()
        )
        return [self._serialize(t) for t in tickets]

    def get_all_tickets(
        self, db: Session, status_filter: str = "", category_filter: str = "", limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Admin view: list all support tickets with filters."""
        q = db.query(SupportTicketDB)
        if status_filter:
            q = q.filter(SupportTicketDB.status == status_filter.upper())
        if category_filter:
            q = q.filter(SupportTicketDB.category == category_filter.upper())

        tickets = q.order_by(SupportTicketDB.created_at.desc()).limit(limit).all()
        return [self._serialize(t, include_user=True) for t in tickets]

    def reply_ticket(
        self, db: Session, ticket_id: str, reply_text: str, new_status: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Admin responds to ticket and optionally updates status."""
        ticket = db.query(SupportTicketDB).filter(SupportTicketDB.id == ticket_id).first()
        if not ticket:
            return False, "Ticket not found."

        clean_reply = self.sanitize_text(reply_text)
        ticket.admin_reply = clean_reply
        if new_status:
            ticket.status = new_status.upper()
        ticket.updated_at = _utcnow()

        db.commit()
        return True, "Reply submitted."

    def add_customer_reply(
        self, db: Session, ticket_id: str, user_id: str, reply_text: str
    ) -> Tuple[bool, str]:
        """Customer sends follow-up response in ticket thread."""
        ticket = (
            db.query(SupportTicketDB)
            .filter(SupportTicketDB.id == ticket_id, SupportTicketDB.user_id == user_id)
            .first()
        )
        if not ticket:
            return False, "Ticket not found or unauthorized."

        clean_reply = self.sanitize_text(reply_text)
        existing = ticket.user_reply or ""
        ticket.user_reply = f"{existing}\n{clean_reply}".strip() if existing else clean_reply
        ticket.status = "OPEN"  # Re-opens ticket for staff attention
        ticket.updated_at = _utcnow()
        db.commit()
        return True, "Response sent to support team."

    def add_internal_note(
        self, db: Session, ticket_id: str, staff_id: str, note_text: str
    ) -> Tuple[bool, str]:
        """Add staff-only internal note. Strictly never sent to customer."""
        ticket = db.query(SupportTicketDB).filter(SupportTicketDB.id == ticket_id).first()
        if not ticket:
            return False, "Ticket not found."

        timestamp_str = _utcnow().strftime("%Y-%m-%d %H:%M UTC")
        entry = f"[{timestamp_str} by {staff_id}]: {self.sanitize_text(note_text)}"
        existing = ticket.internal_notes or ""
        ticket.internal_notes = f"{existing}\n{entry}".strip() if existing else entry
        ticket.updated_at = _utcnow()
        db.commit()
        return True, "Internal staff note saved."

    def update_status(self, db: Session, ticket_id: str, new_status: str) -> Tuple[bool, str]:
        """Update ticket resolution status."""
        ticket = db.query(SupportTicketDB).filter(SupportTicketDB.id == ticket_id).first()
        if not ticket:
            return False, "Ticket not found."

        ticket.status = new_status.upper()
        ticket.updated_at = _utcnow()
        db.commit()
        return True, f"Status updated to {ticket.status}."

    def get_all_tickets(
        self, db: Session, status_filter: str = "", category_filter: str = "", limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Admin view: list all support tickets with filters, including internal notes."""
        q = db.query(SupportTicketDB)
        if status_filter:
            q = q.filter(SupportTicketDB.status == status_filter.upper())
        if category_filter:
            q = q.filter(SupportTicketDB.category == category_filter.upper())

        tickets = q.order_by(SupportTicketDB.created_at.desc()).limit(limit).all()
        return [self._serialize(t, include_user=True, include_internal_notes=True) for t in tickets]

    @staticmethod
    def _serialize(
        t: SupportTicketDB, include_user: bool = False, include_internal_notes: bool = False
    ) -> Dict[str, Any]:
        data = {
            "id": t.id,
            "ticket_number": t.ticket_number,
            "user_id": t.user_id,
            "subject": t.subject,
            "category": t.category,
            "error_id": t.error_id,
            "related_crash_id": getattr(t, "related_crash_id", None),
            "related_incident_id": getattr(t, "related_incident_id", None),
            "app_version": t.app_version,
            "os_version": t.os_version,
            "subscription_status": t.subscription_status,
            "message": t.message,
            "user_reply": t.user_reply,
            "admin_reply": t.admin_reply,
            "status": t.status,
            "priority": t.priority,
            "diagnostics": json.loads(t.diagnostics_json or "{}"),
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        if include_internal_notes:
            data["internal_notes"] = t.internal_notes or ""
        if include_user and t.user:
            data["user_email"] = t.user.email
            data["user_name"] = t.user.display_name
        return data

    # ── Incident Grouping Engine ─────────────────────────────────────────────

    def record_crash_incident(self, db: Session, crash_data: Dict[str, Any]) -> Tuple[IncidentDB, bool]:
        """Group crashes by stack signature.
        If 500 users encounter the same defect, update the single incident.
        """
        raw_sig = crash_data.get("stack_signature") or "generic_sig"
        exc_type = crash_data.get("error_type") or "Exception"
        component = crash_data.get("component") or "core"
        app_ver = crash_data.get("app_version") or "1.0.0"
        user_id = crash_data.get("user_id") or crash_data.get("device_id_ref") or "anonymous"
        error_msg = crash_data.get("sanitized_message") or "Unknown error"
        level = crash_data.get("error_level", "ERROR")

        incident = db.query(IncidentDB).filter(IncidentDB.crash_signature == raw_sig).first()

        if incident:
            # Existing incident: update occurrence and affected users/versions
            incident.occurrences += 1
            incident.last_seen = _utcnow()

            users = json.loads(incident.affected_users_json or "[]")
            if user_id not in users:
                users.append(user_id)
                incident.affected_users_count = len(users)
                incident.affected_users_json = json.dumps(users)

            versions = json.loads(incident.affected_versions_json or "[]")
            if app_ver not in versions:
                versions.append(app_ver)
                incident.affected_versions_json = json.dumps(versions)

            db.commit()
            db.refresh(incident)
            return incident, False
        else:
            # New incident
            inc_num = f"CRASH-{uuid.uuid4().hex[:4].upper()}"
            title = f"{component}: {exc_type} - {error_msg[:60]}"
            sev = IncidentSeverity.SEV2.value
            if level in ("FATAL", "CRITICAL"):
                sev = IncidentSeverity.SEV1.value

            incident = IncidentDB(
                id=f"inc_{uuid.uuid4().hex[:16]}",
                incident_number=inc_num,
                crash_signature=raw_sig,
                title=title,
                component=component,
                error_type=exc_type,
                severity=sev,
                status=IncidentStatus.NEW.value,
                first_seen=_utcnow(),
                last_seen=_utcnow(),
                occurrences=1,
                affected_users_count=1,
                affected_users_json=json.dumps([user_id]),
                affected_versions_json=json.dumps([app_ver]),
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            db.add(incident)
            db.commit()
            db.refresh(incident)
            return incident, True

    def get_incidents(
        self, db: Session, status_filter: str = "", severity_filter: str = "", limit: int = 50
    ) -> List[Dict[str, Any]]:
        """List grouped incidents with filtering."""
        q = db.query(IncidentDB)
        if status_filter:
            q = q.filter(IncidentDB.status == status_filter.upper())
        if severity_filter:
            q = q.filter(IncidentDB.severity == severity_filter.upper())

        incidents = q.order_by(IncidentDB.last_seen.desc()).limit(limit).all()
        return [self._serialize_incident(i) for i in incidents]

    def update_incident(
        self,
        db: Session,
        incident_id: str,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        fixed_in_version: Optional[str] = None,
        assigned_owner: Optional[str] = None,
        workaround: Optional[str] = None,
        engineering_notes: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Update engineering incident properties."""
        inc = db.query(IncidentDB).filter(IncidentDB.id == incident_id).first()
        if not inc:
            return False, "Incident not found.", None

        if status:
            inc.status = status.upper()
        if severity:
            inc.severity = severity.upper()
        if fixed_in_version is not None:
            inc.fixed_in_version = fixed_in_version
        if assigned_owner is not None:
            inc.assigned_owner = assigned_owner
        if workaround is not None:
            inc.workaround = self.sanitize_text(workaround)
        if engineering_notes is not None:
            inc.engineering_notes = self.sanitize_text(engineering_notes)

        inc.updated_at = _utcnow()
        db.commit()
        db.refresh(inc)
        return True, "Incident updated.", self._serialize_incident(inc)

    def link_ticket_to_incident(
        self, db: Session, ticket_id: str, incident_id: str
    ) -> Tuple[bool, str]:
        """Link customer ticket to known engineering incident."""
        ticket = db.query(SupportTicketDB).filter(SupportTicketDB.id == ticket_id).first()
        if not ticket:
            return False, "Ticket not found."
        ticket.related_incident_id = incident_id
        ticket.updated_at = _utcnow()
        db.commit()
        return True, "Ticket linked to incident."

    def get_known_issues(self, db: Session, user_version: str = "") -> List[Dict[str, Any]]:
        """Return published known issues with optional version-specific alert flag."""
        incidents = (
            db.query(IncidentDB)
            .filter(IncidentDB.status.in_([IncidentStatus.NEW.value, IncidentStatus.INVESTIGATING.value, IncidentStatus.MITIGATED.value]))
            .all()
        )
        results = []
        for inc in incidents:
            if not inc.workaround and not inc.title:
                continue
            versions = json.loads(inc.affected_versions_json or "[]")
            affects_current = user_version in versions if user_version else False
            results.append({
                "incident_number": inc.incident_number,
                "title": inc.title,
                "status": inc.status,
                "affected_versions": versions,
                "affects_user_version": affects_current,
                "workaround": inc.workaround or "Under active investigation by engineering.",
                "fixed_in_version": inc.fixed_in_version,
            })
        return results

    def get_incident_analytics(self, db: Session) -> Dict[str, Any]:
        """Aggregate crash occurrences, affected users, top crashes, and version correlation."""
        incidents = db.query(IncidentDB).all()
        total_crashes = sum(i.occurrences for i in incidents)
        total_affected_users = sum(i.affected_users_count for i in incidents)

        top_crashes = sorted(incidents, key=lambda x: x.occurrences, reverse=True)[:5]
        version_counts: Dict[str, int] = {}
        for inc in incidents:
            versions = json.loads(inc.affected_versions_json or "[]")
            for v in versions:
                version_counts[v] = version_counts.get(v, 0) + inc.occurrences

        top_versions = sorted(version_counts.items(), key=lambda x: x[1], reverse=True)

        return {
            "total_incidents": len(incidents),
            "total_crashes": total_crashes,
            "total_affected_users": total_affected_users,
            "top_crashes": [self._serialize_incident(i) for i in top_crashes],
            "top_versions": [{"version": v, "crash_count": c} for v, c in top_versions],
        }

    # ── Remote Diagnostic Request & Consent Workflow ─────────────────────────

    def create_diagnostic_request(
        self, db: Session, ticket_id: str, staff_id: str, categories: Optional[List[str]] = None
    ) -> Tuple[bool, str, Optional[DiagnosticRequestDB]]:
        """Support staff requests updated technical diagnostics from customer."""
        ticket = db.query(SupportTicketDB).filter(SupportTicketDB.id == ticket_id).first()
        if not ticket:
            return False, "Ticket not found.", None

        req = DiagnosticRequestDB(
            id=f"diagreq_{uuid.uuid4().hex[:16]}",
            ticket_id=ticket.id,
            user_id=ticket.user_id,
            requested_by=staff_id,
            status=DiagnosticRequestStatus.PENDING.value,
            requested_categories_json=json.dumps(categories or ["system_info", "health", "sanitized_logs"]),
            requested_at=_utcnow(),
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        return True, "Diagnostic request sent to customer.", req

    def respond_diagnostic_request(
        self,
        db: Session,
        request_id: str,
        user_id: str,
        approved: bool,
        diagnostic_bundle: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """Customer approves and sends, or explicitly declines the diagnostic request."""
        req = (
            db.query(DiagnosticRequestDB)
            .filter(DiagnosticRequestDB.id == request_id, DiagnosticRequestDB.user_id == user_id)
            .first()
        )
        if not req:
            return False, "Diagnostic request not found or unauthorized."

        if not approved:
            req.status = DiagnosticRequestStatus.DECLINED.value
            req.responded_at = _utcnow()
            db.commit()
            return True, "Diagnostic request declined. Zero technical data transmitted."

        # Customer approved: sanitize and attach bundle
        clean_bundle = self.sanitize_diagnostics(diagnostic_bundle or {})
        req.status = DiagnosticRequestStatus.APPROVED.value
        req.diagnostic_bundle_id = clean_bundle.get("bundle_id", f"BND-{uuid.uuid4().hex[:6]}")
        req.responded_at = _utcnow()

        ticket = db.query(SupportTicketDB).filter(SupportTicketDB.id == req.ticket_id).first()
        if ticket:
            ticket.diagnostics_json = json.dumps(clean_bundle)
            ticket.updated_at = _utcnow()

        db.commit()
        return True, "Diagnostic bundle verified, sanitized, and attached to ticket."

    @staticmethod
    def _serialize_incident(i: IncidentDB) -> Dict[str, Any]:
        return {
            "id": i.id,
            "incident_number": i.incident_number,
            "crash_signature": i.crash_signature,
            "title": i.title,
            "component": i.component,
            "error_type": i.error_type,
            "severity": i.severity,
            "status": i.status,
            "first_seen": i.first_seen.isoformat() if i.first_seen else None,
            "last_seen": i.last_seen.isoformat() if i.last_seen else None,
            "occurrences": i.occurrences,
            "affected_users_count": i.affected_users_count,
            "affected_versions": json.loads(i.affected_versions_json or "[]"),
            "fixed_in_version": i.fixed_in_version,
            "assigned_owner": i.assigned_owner,
            "workaround": i.workaround,
            "engineering_notes": i.engineering_notes,
            "created_at": i.created_at.isoformat() if i.created_at else None,
            "updated_at": i.updated_at.isoformat() if i.updated_at else None,
        }

