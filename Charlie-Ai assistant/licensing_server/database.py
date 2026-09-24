"""
licensing_server/database.py — SQLAlchemy ORM models and database session management.

Tables: users, subscriptions, devices, signed_entitlements, payments, license_events, transfer_events.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from .config import config


class Base(DeclarativeBase):
    pass


# ── Enums ────────────────────────────────────────────────────────────────────

class PlanTier(str, enum.Enum):
    STARTER = "STARTER"
    BASIC = "BASIC"
    PREMIUM = "PREMIUM"
    ADVANCED = "ADVANCED"
    PRO = "PRO"
    PRO_PLUS = "PRO_PLUS"
    ANNUAL_PRO = "ANNUAL_PRO"
    LIFETIME = "LIFETIME"


class SubscriptionStatus(str, enum.Enum):
    FREE = "FREE"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    GRACE_PERIOD = "GRACE_PERIOD"
    CANCEL_AT_PERIOD_END = "CANCEL_AT_PERIOD_END"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    SUSPENDED = "SUSPENDED"
    LIFETIME_ACTIVE = "LIFETIME_ACTIVE"


class DeviceStatusEnum(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    REVOKED = "REVOKED"
    TRANSFER_PENDING = "TRANSFER_PENDING"


class ReleaseStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    READY = "READY"
    PUBLISHED = "PUBLISHED"
    PAUSED = "PAUSED"
    REVOKED = "REVOKED"


class ReleaseChannelEnum(str, enum.Enum):
    STABLE = "STABLE"
    BETA = "BETA"
    INTERNAL = "INTERNAL"


class UserRole(str, enum.Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    SUPPORT = "SUPPORT"
    CUSTOMER = "CUSTOMER"
    USER = "USER"  # Backward compatibility alias for CUSTOMER


class AccountStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    BANNED = "BANNED"


class SupportCategory(str, enum.Enum):
    LOGIN = "LOGIN"
    PAYMENT = "PAYMENT"
    SUBSCRIPTION = "SUBSCRIPTION"
    DEVICE_ACTIVATION = "DEVICE_ACTIVATION"
    LICENSE_TRANSFER = "LICENSE_TRANSFER"
    APP_CRASH = "APP_CRASH"
    VOICE = "VOICE"
    AI = "AI"
    FILMORA = "FILMORA"
    UPDATE = "UPDATE"
    OTHER = "OTHER"


class IncidentSeverity(str, enum.Enum):
    SEV0 = "SEV0"  # Critical security or data loss
    SEV1 = "SEV1"  # Major outage / broad startup failure
    SEV2 = "SEV2"  # Subsystem or feature failure
    SEV3 = "SEV3"  # Minor / local defect


class IncidentStatus(str, enum.Enum):
    NEW = "NEW"
    INVESTIGATING = "INVESTIGATING"
    MITIGATED = "MITIGATED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class DiagnosticRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"


class LicenseEventType(str, enum.Enum):
    DEVICE_ACTIVATED = "DEVICE_ACTIVATED"
    DEVICE_DEACTIVATED = "DEVICE_DEACTIVATED"
    LICENSE_TRANSFERRED = "LICENSE_TRANSFERRED"
    LOGIN = "LOGIN"
    LICENSE_REFRESH = "LICENSE_REFRESH"
    PAYMENT_VERIFIED = "PAYMENT_VERIFIED"
    SUBSCRIPTION_CHANGED = "SUBSCRIPTION_CHANGED"
    LICENSE_REVOKED = "LICENSE_REVOKED"
    TAMPER_DETECTED = "TAMPER_DETECTED"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Tables ───────────────────────────────────────────────────────────────────

class UserDB(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(128), default="JARVIS User")
    role = Column(String(20), default=UserRole.CUSTOMER.value)  # OWNER, ADMIN, SUPPORT, CUSTOMER, USER
    session_version = Column(Integer, default=1)
    account_status = Column(String(20), default=AccountStatus.ACTIVE.value)
    internal_notes = Column(Text, nullable=True)  # Admin/Staff notes only
    tags = Column(String(255), nullable=True)  # VIP, Beta Tester, etc.
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    last_login = Column(DateTime(timezone=True), nullable=True)

    subscription = relationship("SubscriptionDB", back_populates="user", uselist=False)
    devices = relationship("DeviceDB", back_populates="user")
    support_tickets = relationship("SupportTicketDB", back_populates="user")


class SubscriptionDB(Base):
    __tablename__ = "subscriptions"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), unique=True, nullable=False)
    plan = Column(String(20), default=PlanTier.STARTER.value)
    status = Column(String(30), default=SubscriptionStatus.FREE.value)
    legacy_lifetime = Column(Boolean, default=False)
    billing_interval = Column(String(20), default="monthly")
    credits_allocated = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True), default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    payment_reference = Column(String(128), nullable=True)
    device_limit = Column(Integer, default=1)
    active_device_id = Column(String(64), nullable=True)

    user = relationship("UserDB", back_populates="subscription")
    wallet = relationship("CreditWalletDB", back_populates="subscription", uselist=False)


class DeviceDB(Base):
    __tablename__ = "devices"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    device_public_key = Column(Text, nullable=True)
    fingerprint_hash = Column(String(128), nullable=False)
    device_name = Column(String(128), default="Unknown PC")
    os_type = Column(String(32), default="Windows")
    app_version = Column(String(20), default="1.0.0")
    status = Column(String(20), default=DeviceStatusEnum.INACTIVE.value)
    security_flag = Column(String(32), default="NORMAL")  # NORMAL, REVIEW_REQUIRED, SUSPICIOUS, BLOCKED
    activated_at = Column(DateTime(timezone=True), nullable=True)
    last_seen = Column(DateTime(timezone=True), default=_utcnow)

    user = relationship("UserDB", back_populates="devices")


class SignedEntitlementDB(Base):
    __tablename__ = "signed_entitlements"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    subscription_id = Column(String(64), ForeignKey("subscriptions.id"), nullable=False)
    device_id = Column(String(64), ForeignKey("devices.id"), nullable=False)
    plan = Column(String(20), nullable=False)
    features_json = Column(Text, nullable=False)
    issued_at = Column(DateTime(timezone=True), default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revalidation_at = Column(DateTime(timezone=True), nullable=False)
    license_type = Column(String(20), default="MONTHLY")
    signature = Column(Text, nullable=False)


class PaymentDB(Base):
    __tablename__ = "payments"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    provider = Column(String(32), default="razorpay")
    order_id = Column(String(128), nullable=True)
    payment_id = Column(String(128), nullable=True)
    idempotency_key = Column(String(128), unique=True, nullable=True, index=True)
    amount_paise = Column(Integer, nullable=False)
    plan = Column(String(20), nullable=False)
    status = Column(String(20), default="PENDING")
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class LicenseEventDB(Base):
    __tablename__ = "license_events"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    device_id = Column(String(64), nullable=True)
    event_type = Column(String(30), nullable=False)
    details_json = Column(Text, default="{}")
    timestamp = Column(DateTime(timezone=True), default=_utcnow)


class TransferEventDB(Base):
    __tablename__ = "transfer_events"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    from_device_id = Column(String(64), nullable=False)
    to_device_id = Column(String(64), nullable=False)
    transferred_at = Column(DateTime(timezone=True), default=_utcnow)


class SupportTicketDB(Base):
    __tablename__ = "support_tickets"

    id = Column(String(64), primary_key=True)
    ticket_number = Column(String(32), unique=True, nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    subject = Column(String(255), nullable=False)
    category = Column(String(50), default=SupportCategory.OTHER.value)
    error_id = Column(String(64), nullable=True)
    related_crash_id = Column(String(64), nullable=True, index=True)
    related_incident_id = Column(String(64), nullable=True, index=True)
    app_version = Column(String(20), default="1.0.0")
    os_version = Column(String(64), default="Windows")
    subscription_status = Column(String(30), nullable=True)
    diagnostics_json = Column(Text, default="{}")  # Sanitized logs & safe diagnostics
    message = Column(Text, nullable=False)
    user_reply = Column(Text, nullable=True)
    admin_reply = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)  # Staff only — NEVER sent to customer
    status = Column(String(20), default="OPEN")  # OPEN, IN_PROGRESS, WAITING_FOR_CUSTOMER, RESOLVED, CLOSED
    priority = Column(String(20), default="NORMAL")  # LOW, NORMAL, HIGH, URGENT
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user = relationship("UserDB", back_populates="support_tickets")


class IncidentDB(Base):
    __tablename__ = "incidents"

    id = Column(String(64), primary_key=True)
    incident_number = Column(String(32), unique=True, nullable=False, index=True)
    crash_signature = Column(String(64), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    component = Column(String(64), default="core", index=True)
    error_type = Column(String(64), default="Exception")
    severity = Column(String(20), default=IncidentSeverity.SEV2.value, index=True)
    status = Column(String(20), default=IncidentStatus.NEW.value, index=True)
    first_seen = Column(DateTime(timezone=True), default=_utcnow)
    last_seen = Column(DateTime(timezone=True), default=_utcnow)
    occurrences = Column(Integer, default=1)
    affected_users_count = Column(Integer, default=1)
    affected_users_json = Column(Text, default="[]")
    affected_versions_json = Column(Text, default="[]")
    fixed_in_version = Column(String(20), nullable=True)
    assigned_owner = Column(String(64), nullable=True)
    workaround = Column(Text, nullable=True)
    engineering_notes = Column(Text, nullable=True)  # Strictly internal notes
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class DiagnosticRequestDB(Base):
    __tablename__ = "diagnostic_requests"

    id = Column(String(64), primary_key=True)
    ticket_id = Column(String(64), ForeignKey("support_tickets.id"), nullable=False)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    requested_by = Column(String(64), nullable=False)
    status = Column(String(20), default=DiagnosticRequestStatus.PENDING.value, index=True)
    requested_categories_json = Column(Text, default='["system_info", "health", "sanitized_logs"]')
    diagnostic_bundle_id = Column(String(64), nullable=True)
    requested_at = Column(DateTime(timezone=True), default=_utcnow)
    responded_at = Column(DateTime(timezone=True), nullable=True)



class AuditLogDB(Base):
    __tablename__ = "audit_logs"

    id = Column(String(64), primary_key=True)
    actor_id = Column(String(64), nullable=False)  # Admin user ID or "SYSTEM"
    action = Column(String(64), nullable=False)  # SUSPEND_USER, RESET_DEVICE, GRANT_PLAN, etc.
    target_user_id = Column(String(64), nullable=True)
    target_device_id = Column(String(64), nullable=True)
    details_json = Column(Text, default="{}")
    timestamp = Column(DateTime(timezone=True), default=_utcnow)


class UpdateReleaseDB(Base):
    __tablename__ = "update_releases"

    id = Column(String(64), primary_key=True)
    version = Column(String(20), unique=True, nullable=False, index=True)
    build_number = Column(Integer, default=100)
    channel = Column(String(20), default="STABLE", index=True)  # STABLE, BETA, INTERNAL
    status = Column(String(20), default=ReleaseStatus.PUBLISHED.value, index=True)  # DRAFT, VALIDATING, READY, PUBLISHED, PAUSED, REVOKED
    rollout_percentage = Column(Integer, default=100)  # 0 - 100
    download_url = Column(String(255), nullable=False)
    file_size = Column(Integer, default=0)
    sha256 = Column(String(64), nullable=False)
    signature = Column(Text, nullable=True)
    manifest_json = Column(Text, nullable=True)  # Full signed canonical JSON
    release_notes = Column(Text, default="")
    mandatory = Column(Boolean, default=False)
    security_update = Column(Boolean, default=False)
    rollback_supported = Column(Boolean, default=True)
    database_schema_version = Column(Integer, default=1)
    min_supported_version = Column(String(20), default="1.0.0")
    minimum_os_version = Column(String(20), default="10.0")
    created_by = Column(String(64), default="SYSTEM")
    released_at = Column(DateTime(timezone=True), default=_utcnow)


class UpdateTelemetryDB(Base):
    __tablename__ = "update_telemetry"

    id = Column(String(64), primary_key=True)
    event_type = Column(String(50), nullable=False, index=True)
    client_version = Column(String(20), nullable=False)
    target_version = Column(String(20), nullable=False)
    channel = Column(String(20), default="STABLE")
    device_id_hash = Column(String(64), nullable=True)
    details_json = Column(Text, default="{}")
    timestamp = Column(DateTime(timezone=True), default=_utcnow)


class CreditWalletDB(Base):
    __tablename__ = "credit_wallets"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), unique=True, nullable=False)
    subscription_id = Column(String(64), ForeignKey("subscriptions.id"), nullable=True)
    plan_tier = Column(String(32), default=PlanTier.STARTER.value)
    subscription_credits = Column(Integer, default=0)
    purchased_credits = Column(Integer, default=0)
    credits_used = Column(Integer, default=0)
    daily_messages_used = Column(Integer, default=0)
    billing_cycle_start = Column(DateTime(timezone=True), default=_utcnow)
    billing_cycle_end = Column(DateTime(timezone=True), nullable=True)
    last_reset_at = Column(DateTime(timezone=True), default=_utcnow)

    subscription = relationship("SubscriptionDB", back_populates="wallet")


class CreditTransactionDB(Base):
    __tablename__ = "credit_transactions"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(32), nullable=False)  # RESET, USAGE, PURCHASE, BONUS
    amount = Column(Integer, nullable=False)
    source = Column(String(64), nullable=False)
    reference_id = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class UsageEventDB(Base):
    __tablename__ = "usage_events"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False, index=True)
    feature = Column(String(64), nullable=False, index=True)
    model = Column(String(64), nullable=True)
    provider = Column(String(32), nullable=True)  # openai, google, ollama, local
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    credits_used = Column(Integer, default=1)
    estimated_provider_cost = Column(Float, default=0.0)  # INR
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class RazorpayEventDB(Base):
    __tablename__ = "razorpay_events"

    id = Column(String(128), primary_key=True)  # Razorpay event id for idempotency
    event_type = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    processed_at = Column(DateTime(timezone=True), default=_utcnow)


import json
import logging
import time
from sqlalchemy import event

engine = create_engine(config.DATABASE_URL, echo=config.DEBUG, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

db_logger = logging.getLogger("licensing_server.db")
SLOW_QUERY_THRESHOLD_MS = 50.0

@event.listens_for(engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault("query_start_time", []).append(time.perf_counter())

@event.listens_for(engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    times = conn.info.get("query_start_time")
    if times:
        duration_ms = round((time.perf_counter() - times.pop()) * 1000, 2)
        if duration_ms >= SLOW_QUERY_THRESHOLD_MS:
            db_logger.warning(
                json.dumps({
                    "timestamp": _utcnow().isoformat(),
                    "level": "WARN",
                    "service": "jarvis-licensing-db",
                    "event": "SLOW_QUERY",
                    "duration_ms": duration_ms,
                    "statement": str(statement)[:200],
                })
            )

def init_db() -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Dependency injection for FastAPI routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
