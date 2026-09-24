"""engine.research — Deep Research, Internet Intelligence, and Content Intelligence Engine."""

from engine.research.bridge import ResearchToActionBridge
from engine.research.collector import PageReader, RecencyEngine, SourceCollector, SourceEvaluator
from engine.research.content_engine import (
    ContentBrief,
    FactLock,
    HookGenerator,
    TitleIntelligence,
    YouTubeIntelligenceEngine,
)
from engine.research.engine import InternetIntelligenceEngine
from engine.research.fact_checker import (
    ClaimExtractor,
    CitationManager,
    ContradictionDetector,
    FactVerificationEngine,
)
from engine.research.guard import UntrustedContentGuard
from engine.research.memory import ResearchMemoryManager
from engine.research.models import (
    AtomicClaim,
    Citation,
    ClaimEvidenceMap,
    ConfidenceLevel,
    ContradictionRecord,
    ResearchBudget,
    ResearchIntent,
    ResearchMode,
    ResearchPlan,
    ResearchReport,
    SourceRecord,
    SourceType,
    TrendCandidate,
    VerificationStatus,
)
from engine.research.planner import (
    QueryGenerator,
    ResearchIntentClassifier,
    ResearchPlanner,
    TimeSensitivityDetector,
)
from engine.research.providers import (
    DuckDuckGoSearchProvider,
    GeminiSearchProvider,
    MockSearchProvider,
    SearchProvider,
    SearchProviderManager,
)
from engine.research.synthesizer import ResearchSynthesizer
from engine.research.trend_engine import TopicClusterer, TrendDiscoveryEngine

__all__ = [
    "InternetIntelligenceEngine",
    "ResearchPlanner",
    "ResearchIntentClassifier",
    "TimeSensitivityDetector",
    "QueryGenerator",
    "SearchProvider",
    "SearchProviderManager",
    "DuckDuckGoSearchProvider",
    "GeminiSearchProvider",
    "MockSearchProvider",
    "SourceCollector",
    "PageReader",
    "SourceEvaluator",
    "RecencyEngine",
    "ClaimExtractor",
    "FactVerificationEngine",
    "ContradictionDetector",
    "CitationManager",
    "ResearchSynthesizer",
    "ResearchMemoryManager",
    "UntrustedContentGuard",
    "TrendDiscoveryEngine",
    "TopicClusterer",
    "YouTubeIntelligenceEngine",
    "HookGenerator",
    "TitleIntelligence",
    "ContentBrief",
    "FactLock",
    "ResearchToActionBridge",
    "ResearchIntent",
    "ResearchMode",
    "SourceType",
    "VerificationStatus",
    "ConfidenceLevel",
    "ResearchBudget",
    "SourceRecord",
    "AtomicClaim",
    "ClaimEvidenceMap",
    "ContradictionRecord",
    "Citation",
    "ResearchPlan",
    "ResearchReport",
    "TrendCandidate",
]
