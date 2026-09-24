"""
engine/commercial/models.py — Commercial Monetization, Licensing, and Entitlement Domain Models.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


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


class BillingCycle(str, enum.Enum):
    FREE = "FREE"
    MONTHLY = "MONTHLY"
    ANNUAL = "ANNUAL"
    ONE_TIME = "ONE_TIME"


class Entitlement(str, enum.Enum):
    VOICE_MALE = "VOICE_MALE"
    VOICE_FEMALE = "VOICE_FEMALE"
    VOICE_MULTIPLE = "VOICE_MULTIPLE"
    TEXT_CHAT = "TEXT_CHAT"
    COMPUTER_BASIC = "COMPUTER_BASIC"
    COMPUTER_ADVANCED = "COMPUTER_ADVANCED"
    MEMORY_BASIC = "MEMORY_BASIC"
    MEMORY_ADVANCED = "MEMORY_ADVANCED"
    KNOWLEDGE_GRAPH = "KNOWLEDGE_GRAPH"
    RESEARCH_BASIC = "RESEARCH_BASIC"
    RESEARCH_DEEP = "RESEARCH_DEEP"
    CODING = "CODING"
    AUTONOMY_ADVANCED = "AUTONOMY_ADVANCED"
    MULTI_AGENT = "MULTI_AGENT"
    SPREADSHEET_BASIC = "SPREADSHEET_BASIC"
    SPREADSHEET_ADVANCED = "SPREADSHEET_ADVANCED"
    GMAIL = "GMAIL"
    CALENDAR = "CALENDAR"
    DRIVE = "DRIVE"
    VIDEO_BASIC = "VIDEO_BASIC"
    VIDEO_FILMORA = "VIDEO_FILMORA"
    YOUTUBE_AUTOMATION = "YOUTUBE_AUTOMATION"
    SKILLS_BASIC = "SKILLS_BASIC"
    SKILL_LEARNING = "SKILL_LEARNING"
    PLUGINS = "PLUGINS"
    MCP = "MCP"
    CUSTOM_AGENTS = "CUSTOM_AGENTS"
    MULTI_DEVICE = "MULTI_DEVICE"
    OFFLINE_AI = "OFFLINE_AI"
    PROACTIVE_INTELLIGENCE = "PROACTIVE_INTELLIGENCE"


class DeviceStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    REVOKED = "REVOKED"
    TRANSFER_PENDING = "TRANSFER_PENDING"


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


class GateStatus(str, enum.Enum):
    ALLOWED = "ALLOWED"
    LIMIT_REACHED = "LIMIT_REACHED"
    PLAN_REQUIRED = "PLAN_REQUIRED"
    SUBSCRIPTION_EXPIRED = "SUBSCRIPTION_EXPIRED"
    OFFLINE_LICENSE_REQUIRED = "OFFLINE_LICENSE_REQUIRED"
    ACCOUNT_REQUIRED = "ACCOUNT_REQUIRED"
    DEVICE_NOT_ACTIVATED = "DEVICE_NOT_ACTIVATED"
    DEVICE_MISMATCH = "DEVICE_MISMATCH"
    ENTITLEMENT_INVALID = "ENTITLEMENT_INVALID"


class UsageState(str, enum.Enum):
    SESSION_STARTED = "SESSION_STARTED"
    ACTIVE = "ACTIVE"
    IDLE = "IDLE"
    PAUSED = "PAUSED"
    ENDED = "ENDED"


class CloudComputeMode(str, enum.Enum):
    INCLUDED_QUOTA = "INCLUDED_QUOTA"
    LOCAL_AI = "LOCAL_AI"
    BYOK = "BYOK"
    OPTIONAL_USAGE_PACK = "OPTIONAL_USAGE_PACK"


@dataclass
class PlanDefinition:
    tier: PlanTier
    name: str
    price_inr: int  # in whole INR (e.g. 0, 149, 299, 599, 2999)
    billing_cycle: BillingCycle
    tagline: str
    benefits: List[str]
    entitlements: List[Entitlement]
    daily_active_minutes_limit: Optional[int] = None
    daily_messages_limit: Optional[int] = None
    monthly_credits: int = 0
    max_devices: int = 1
    badge: Optional[str] = None
    cloud_fair_use_tokens: int = 0
    is_recurring: bool = False
    regular_annual_cost: Optional[int] = None
    annual_saving_inr: Optional[int] = None
    annual_saving_pct: Optional[float] = None
    effective_monthly_inr: Optional[float] = None


@dataclass
class CreditWallet:
    user_id: str
    plan_tier: PlanTier = PlanTier.STARTER
    subscription_credits: int = 0
    purchased_credits: int = 0
    daily_messages_used: int = 0
    billing_cycle_start: Optional[datetime] = None
    billing_cycle_end: Optional[datetime] = None
    last_reset_at: Optional[datetime] = None

    @property
    def total_credits(self) -> int:
        return self.subscription_credits + self.purchased_credits


@dataclass
class CreditTransaction:
    id: str
    user_id: str
    type: str  # RESET, USAGE, PURCHASE, BONUS
    amount: int
    source: str
    reference_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class GateResult:
    status: GateStatus
    allowed: bool
    entitlement: Entitlement
    required_plan: Optional[PlanTier] = None
    reason: str = ""
    retry_after_sec: Optional[int] = None


@dataclass
class UserAccount:
    user_id: str
    display_name: str = ""
    email: str = ""
    plan: PlanTier = PlanTier.STARTER
    subscription_status: SubscriptionStatus = SubscriptionStatus.FREE
    legacy_lifetime: bool = False
    billing_customer_id: Optional[str] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_entitlement_sync: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    activated_devices: List[str] = field(default_factory=list)
    credit_wallet: Optional[CreditWallet] = None

    def __post_init__(self):
        if self.plan != PlanTier.STARTER and self.subscription_status == SubscriptionStatus.FREE:
            self.subscription_status = SubscriptionStatus.ACTIVE


@dataclass
class SignedLicense:
    user_id: str
    plan: PlanTier
    issued_at: str  # ISO timestamp
    valid_until: str  # ISO timestamp
    features: List[str]
    device_id: str
    signature: str


@dataclass
class PaymentReceipt:
    receipt_id: str
    transaction_id: str
    order_id: str
    user_id: str
    plan: PlanTier
    amount_paise: int  # Smallest currency unit (INR Paise)
    currency: str = "INR"
    status: str = "PAID"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payment_method: str = "UPI"


@dataclass
class PaymentCheckoutSession:
    session_id: str
    order_id: str
    plan: PlanTier
    amount_paise: int
    currency: str = "INR"
    checkout_url: str = ""
    client_secret: Optional[str] = None
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DeviceLicenseRecord:
    device_id: str
    device_name: str
    user_id: str
    plan: PlanTier
    activated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    revoked: bool = False


@dataclass
class ServerSignedEntitlement:
    """Entitlement issued and signed by the licensing server (RSA-2048).

    Stored locally as offline cache. Verified with embedded public key.
    """
    user_id: str = ""
    subscription_id: str = ""
    plan: PlanTier = PlanTier.STARTER
    device_id: str = ""
    features: List[str] = field(default_factory=list)
    issued_at: str = ""
    expires_at: str = ""
    revalidation_at: str = ""
    license_type: str = "MONTHLY"  # "MONTHLY" | "LIFETIME"
    token: str = ""  # Combined payload.signature portable token

