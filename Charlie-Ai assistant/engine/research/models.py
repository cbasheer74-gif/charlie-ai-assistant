"""engine/research/models.py — Data Models and Enums for JARVIS Research Intelligence Engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ResearchIntent(str, Enum):
    FACT_LOOKUP = "FACT_LOOKUP"
    CURRENT_EVENT = "CURRENT_EVENT"
    DEEP_RESEARCH = "DEEP_RESEARCH"
    COMPARISON = "COMPARISON"
    TREND_DISCOVERY = "TREND_DISCOVERY"
    PRODUCT_RESEARCH = "PRODUCT_RESEARCH"
    SOFTWARE_RESEARCH = "SOFTWARE_RESEARCH"
    YOUTUBE_TOPIC_RESEARCH = "YOUTUBE_TOPIC_RESEARCH"
    CONTENT_RESEARCH = "CONTENT_RESEARCH"
    COMPETITOR_RESEARCH = "COMPETITOR_RESEARCH"
    MARKET_RESEARCH = "MARKET_RESEARCH"
    HOW_TO_RESEARCH = "HOW_TO_RESEARCH"
    NEWS_MONITORING = "NEWS_MONITORING"
    SOURCE_VERIFICATION = "SOURCE_VERIFICATION"


class ResearchMode(str, Enum):
    QUICK = "QUICK"
    STANDARD = "STANDARD"
    DEEP = "DEEP"


class SourceType(str, Enum):
    PRIMARY_SOURCE = "PRIMARY_SOURCE"
    AUTHORITATIVE_SOURCE = "AUTHORITATIVE_SOURCE"
    REPUTABLE_REPORTING = "REPUTABLE_REPORTING"
    SPECIALIST_SOURCE = "SPECIALIST_SOURCE"
    COMMUNITY_SOURCE = "COMMUNITY_SOURCE"
    UNKNOWN_SOURCE = "UNKNOWN_SOURCE"


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    WELL_SUPPORTED = "WELL_SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNVERIFIED = "UNVERIFIED"
    CONFLICTING = "CONFLICTING"
    OUTDATED = "OUTDATED"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class ResearchBudget:
    max_queries: int = 5
    max_sources: int = 15
    max_pages: int = 8
    max_retries: int = 2
    max_research_depth: int = 3
    max_execution_time: float = 60.0


@dataclass
class SourceRecord:
    url: str
    title: str
    domain: str
    snippet: str = ""
    author: Optional[str] = None
    published_at: Optional[str] = None
    updated_at: Optional[str] = None
    retrieved_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    source_type: SourceType = SourceType.UNKNOWN_SOURCE
    query: str = ""
    language: str = "en"
    content_hash: str = ""
    raw_content: str = ""
    is_stale: bool = False
    is_primary: bool = False
    syndication_group: Optional[str] = None


@dataclass
class AtomicClaim:
    claim_id: str
    statement: str
    entity: str = ""
    attribute: str = ""
    value: str = ""
    date_context: Optional[str] = None
    source_url: str = ""
    is_numeric: bool = False
    extracted_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


@dataclass
class ContradictionRecord:
    claim_statement: str
    first_source_url: str
    first_value: str
    second_source_url: str
    second_value: str
    dimension: str  # date, number, version, price, feature
    resolution_hint: str = ""


@dataclass
class Citation:
    claim_id: str
    source_id: str
    url: str
    title: str
    publisher: str
    date: Optional[str]
    retrieved_at: str


@dataclass
class ClaimEvidenceMap:
    claim: AtomicClaim
    status: VerificationStatus
    supporting_sources: List[SourceRecord] = field(default_factory=list)
    contradicting_sources: List[SourceRecord] = field(default_factory=list)
    primary_evidence: Optional[SourceRecord] = None
    confidence: ConfidenceLevel = ConfidenceLevel.UNCERTAIN
    recency_note: str = ""


@dataclass
class ResearchPlan:
    goal: str
    intent: ResearchIntent
    mode: ResearchMode
    subquestions: List[str] = field(default_factory=list)
    search_queries: List[str] = field(default_factory=list)
    required_freshness_ttl_sec: int = 86400  # default 24h
    preferred_sources: List[str] = field(default_factory=list)
    min_source_count: int = 2
    budget: ResearchBudget = field(default_factory=ResearchBudget)
    time_sensitive: bool = False
    project_context: Dict[str, Any] = field(default_factory=dict)
    region: str = "GLOBAL"
    language: str = "en"


@dataclass
class ResearchReport:
    research_goal: str
    time_context: str
    summary: str
    established_facts: List[str] = field(default_factory=list)
    recent_developments: List[str] = field(default_factory=list)
    source_claims: List[str] = field(default_factory=list)
    disagreements: List[ContradictionRecord] = field(default_factory=list)
    uncertain_claims: List[str] = field(default_factory=list)
    sources: List[SourceRecord] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    confidence_reason: str = ""
    evidence_map: List[ClaimEvidenceMap] = field(default_factory=list)
    next_actions: List[str] = field(default_factory=list)
    expires_at: Optional[str] = None
    is_reused_from_cache: bool = False


@dataclass
class TrendCandidate:
    topic: str
    summary: str
    first_seen: str
    latest_activity: str
    supporting_sources: List[SourceRecord] = field(default_factory=list)
    signal_sources: List[str] = field(default_factory=list)
    audience_match: float = 0.5
    novelty: float = 0.5
    content_saturation: float = 0.5
    evidence_quality: float = 0.5
    freshness: float = 0.9
    content_angle_options: List[str] = field(default_factory=list)
    cluster_size: int = 1
    region: str = "GLOBAL"
    is_rumour: bool = False


@dataclass
class FactLock:
    approved_claims: List[str] = field(default_factory=list)
    well_supported_claims: List[str] = field(default_factory=list)
    uncertain_claims_to_avoid: List[str] = field(default_factory=list)
    locked_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


@dataclass
class ContentBrief:
    topic: str
    why_now: str
    target_audience: str
    main_angle: str
    verified_facts: List[str] = field(default_factory=list)
    key_sources: List[str] = field(default_factory=list)
    hook_options: List[str] = field(default_factory=list)
    key_points: List[str] = field(default_factory=list)
    visual_ideas: List[str] = field(default_factory=list)
    claims_to_avoid: List[str] = field(default_factory=list)
    target_duration: int = 60
    cta: str = ""
    fact_lock: Optional[FactLock] = None
