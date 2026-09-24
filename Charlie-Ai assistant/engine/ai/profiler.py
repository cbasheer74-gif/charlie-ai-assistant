"""
JARVIS Phase 11: Task Profiler, Complexity Estimator & Privacy Classifier
Inspects user requests, detects deterministic tasks, assigns complexity tiers,
and enforces zero-trust privacy classifications.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .models import ComplexityLevel, ModelCapability, PrivacyLevel, TaskProfile

logger = logging.getLogger("jarvis.ai.profiler")


class ComplexityEstimator:
    """Estimates the reasoning and intelligence tier required for a task."""

    TRIVIAL_PATTERNS = [
        r"^(open|launch|start)\s+[a-zA-Z0-9_\-]+(\.exe)?$",
        r"^(kholo|chalao|band karo)\s+",
        r"^(what time|current time|date|aaj ki date)",
        r"^(\d+\s*[\+\-\*\/]\s*\d+)$",
        r"^(status|pc status|ping)$",
    ]

    EXPERT_PATTERNS = [
        r"(race condition|deadlock|distributed|architect|reconciliation|concurrency|compiler)",
        r"(formal verification|cryptographic proof|memory leak diagnosis|kernel)",
    ]

    HIGH_PATTERNS = [
        r"(debug|fix test|failing tests|refactor class|performance bottleneck|type error)",
        r"(database migration|security audit|vulnerability)",
    ]

    MEDIUM_PATTERNS = [
        r"(write a function|create component|add endpoint|filter array|validation)",
        r"(summarize article|extract tables|compare trends)",
    ]

    @classmethod
    def estimate(cls, prompt: str) -> ComplexityLevel:
        clean = prompt.strip().lower()

        # Check trivial deterministic patterns first
        for pat in cls.TRIVIAL_PATTERNS:
            if re.search(pat, clean):
                return ComplexityLevel.TRIVIAL

        # Check expert
        for pat in cls.EXPERT_PATTERNS:
            if re.search(pat, clean):
                return ComplexityLevel.EXPERT

        # Check high
        for pat in cls.HIGH_PATTERNS:
            if re.search(pat, clean):
                return ComplexityLevel.HIGH

        # Check medium
        for pat in cls.MEDIUM_PATTERNS:
            if re.search(pat, clean):
                return ComplexityLevel.MEDIUM

        # Default to low for general chat/queries
        return ComplexityLevel.LOW


class PrivacyClassifier:
    """Classifies data sensitivity and redacts secrets from AI prompts."""

    SECRET_PATTERNS = [
        r"sk-[a-zA-Z0-9]{20,}",
        r"AIza[0-9A-Za-z\-_]{35}",
        r"ghp_[a-zA-Z0-9]{36}",
        r"(password|passwd|secret)\s*[:=]\s*['\"][^'\"]+['\"]",
        r"bearer\s+[a-zA-Z0-9_\-\.]{20,}",
    ]

    HIGHLY_SENSITIVE_KEYWORDS = [
        "contract",
        "medical",
        "bank statement",
        "tax return",
        "salary",
        "nda",
        "private key",
        "confidential",
    ]

    PRIVATE_KEYWORDS = [
        "source code",
        "backend",
        "my project",
        "zynpay",
        "internal api",
        "database password",
    ]

    @classmethod
    def classify_and_sanitize(cls, text: str) -> Tuple[PrivacyLevel, str, List[str]]:
        """
        Classifies sensitivity level and strips any secret API keys/passwords.
        Returns: (privacy_level, sanitized_text, list_of_redacted_secrets)
        """
        redacted = []
        clean_text = text

        # 1. Search and redact secrets
        for pat in cls.SECRET_PATTERNS:
            matches = re.findall(pat, clean_text, flags=re.IGNORECASE)
            for m in matches:
                if isinstance(m, tuple):
                    m = m[0]
                redacted.append(m)
                clean_text = clean_text.replace(m, "[REDACTED_SECRET]")

        low = text.lower()

        # If direct secrets were detected
        if redacted:
            return PrivacyLevel.SECRET, clean_text, redacted

        # Highly sensitive documents
        if any(w in low for w in cls.HIGHLY_SENSITIVE_KEYWORDS):
            return PrivacyLevel.HIGHLY_SENSITIVE, clean_text, []

        # Private project content
        if any(w in low for w in cls.PRIVATE_KEYWORDS):
            return PrivacyLevel.PRIVATE, clean_text, []

        # Default to internal/public
        if any(w in low for w in ["weather", "news", "trend", "what is", "define", "who is"]):
            return PrivacyLevel.PUBLIC, clean_text, []

        return PrivacyLevel.INTERNAL, clean_text, []


class TaskProfiler:
    """Profiles incoming requests into a structured TaskProfile."""

    def __init__(self):
        self.complexity_estimator = ComplexityEstimator()
        self.privacy_classifier = PrivacyClassifier()

    def profile_task(self, prompt: str, user_metadata: Optional[Dict[str, Any]] = None) -> Tuple[TaskProfile, str]:
        """
        Analyzes user request.
        Returns: (task_profile, sanitized_prompt)
        """
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        meta = user_metadata or {}

        # 1. Privacy & Redaction
        privacy_level, sanitized, redacted = self.privacy_classifier.classify_and_sanitize(prompt)
        # Allow explicit user override if provided
        if "privacy_override" in meta:
            privacy_level = meta["privacy_override"]

        # 2. Complexity
        complexity = self.complexity_estimator.estimate(sanitized)

        # 3. Detect Deterministic Requirement
        is_deterministic = complexity == ComplexityLevel.TRIVIAL or any(
            sanitized.lower().startswith(p) for p in ["open notepad", "kholo chrome", "pc status", "open calc"]
        )

        # 4. Capabilities
        required_caps = [ModelCapability.CHAT]
        task_type = "GENERAL_QUERY"

        low = sanitized.lower()
        if any(w in low for w in ("code", "debug", "test", "race condition", "refactor", "bug")):
            required_caps.append(ModelCapability.CODING)
            required_caps.append(ModelCapability.REASONING)
            task_type = "CODING_DEBUG"
        elif any(w in low for w in ("screen", "screenshot", "error on screen", "image", "look at")):
            required_caps.append(ModelCapability.VISION)
            task_type = "VISION_INSPECT"
        elif any(w in low for w in ("summarize", "contract", "document", "pdf")):
            required_caps.append(ModelCapability.SUMMARIZATION)
            task_type = "DOCUMENT_SUMMARY"
        elif any(w in low for w in ("trend", "latest news", "youtube short")):
            required_caps.append(ModelCapability.RESEARCH_SYNTHESIS)
            task_type = "RESEARCH"

        profile = TaskProfile(
            task_id=task_id,
            task_type=task_type,
            complexity=complexity,
            privacy_level=privacy_level,
            required_capabilities=required_caps,
            estimated_context_tokens=len(sanitized.split()) * 2 + 300,
            estimated_output_tokens=300,
            requires_deterministic_only=is_deterministic,
            redacted_secrets=redacted,
        )

        return profile, sanitized
