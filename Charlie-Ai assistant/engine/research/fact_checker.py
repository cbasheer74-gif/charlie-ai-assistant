"""engine/research/fact_checker.py — Atomic Claim Extraction, Cross-Source Verification, Contradiction Detection, and Citations."""

from __future__ import annotations

import re
import time
from typing import Dict, List, Optional, Set, Tuple

from engine.research.models import (
    AtomicClaim,
    Citation,
    ClaimEvidenceMap,
    ConfidenceLevel,
    ContradictionRecord,
    SourceRecord,
    SourceType,
    VerificationStatus,
)


class ClaimExtractor:
    """Extracts atomic factual claims from article text or search snippets."""

    NUMERIC_PATTERN = re.compile(r"\b(\$?\d[\d,]*(?:\.\d+)?\s*(?:million|billion|trillion|%|percent|fps|gb|mb|ghz|v\d+)?)\b", re.I)
    VERSION_PATTERN = re.compile(r"\b(v\d+(?:\.\d+)+|version\s+\d+(?:\.\d+)?)\b", re.I)

    @staticmethod
    def extract_claims(text: str, source_url: str = "") -> List[AtomicClaim]:
        if not text:
            return []

        # Split into distinct sentences
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        claims = []

        for idx, s in enumerate(sentences):
            s_clean = s.strip()
            if len(s_clean) < 15:
                continue

            # Identify numeric or version claims
            has_num = bool(ClaimExtractor.NUMERIC_PATTERN.search(s_clean))
            has_ver = bool(ClaimExtractor.VERSION_PATTERN.search(s_clean))

            claim_id = f"claim_{idx+1}_{abs(hash(s_clean)) % 10000}"
            claims.append(
                AtomicClaim(
                    claim_id=claim_id,
                    statement=s_clean,
                    source_url=source_url,
                    is_numeric=has_num or has_ver,
                )
            )

        return claims[:10]  # Cap per source to keep verification efficient


class ContradictionDetector:
    """Detects discrepancies in numbers, versions, release dates, or features across sources."""

    @staticmethod
    def detect_conflicts(claim: AtomicClaim, sources: List[SourceRecord]) -> List[ContradictionRecord]:
        conflicts = []
        if not claim.is_numeric or len(sources) < 2:
            return conflicts

        # Extract numbers or versions in primary statement
        claim_nums = set(ClaimExtractor.NUMERIC_PATTERN.findall(claim.statement))
        claim_vers = set(ClaimExtractor.VERSION_PATTERN.findall(claim.statement))

        for src in sources:
            if src.url == claim.source_url:
                continue
            src_nums = set(ClaimExtractor.NUMERIC_PATTERN.findall(src.snippet))
            src_vers = set(ClaimExtractor.VERSION_PATTERN.findall(src.snippet))

            # If discussing same entity but different versions
            if claim_vers and src_vers and not claim_vers.intersection(src_vers):
                conflicts.append(
                    ContradictionRecord(
                        claim_statement=claim.statement,
                        first_source_url=claim.source_url,
                        first_value=", ".join(claim_vers),
                        second_source_url=src.url,
                        second_value=", ".join(src_vers),
                        dimension="version",
                        resolution_hint="Discrepancy may arise from newer release or different product edition",
                    )
                )

            # If numbers differ significantly on similar metrics
            if claim_nums and src_nums and not claim_nums.intersection(src_nums):
                conflicts.append(
                    ContradictionRecord(
                        claim_statement=claim.statement,
                        first_source_url=claim.source_url,
                        first_value=", ".join(claim_nums),
                        second_source_url=src.url,
                        second_value=", ".join(src_nums),
                        dimension="number",
                        resolution_hint="Discrepancy in numeric metrics or pricing; check publication dates",
                    )
                )

        return conflicts


class CitationManager:
    """Stores provenance citations and generates verifiable source bibliographies."""

    def __init__(self):
        self._citations: List[Citation] = []

    def add_citation(self, claim_id: str, source: SourceRecord) -> Citation:
        cit = Citation(
            claim_id=claim_id,
            source_id=f"src_{abs(hash(source.url)) % 10000}",
            url=source.url,
            title=source.title or source.domain,
            publisher=source.domain,
            date=source.published_at,
            retrieved_at=source.retrieved_at,
        )
        self._citations.append(cit)
        return cit

    def get_citations(self) -> List[Citation]:
        return list(self._citations)


class FactVerificationEngine:
    """Verifies atomic claims against independent sources and primary evidence."""

    def __init__(self):
        self.contradiction_detector = ContradictionDetector()
        self.citation_manager = CitationManager()

    def verify_claim(self, claim: AtomicClaim, sources: List[SourceRecord]) -> ClaimEvidenceMap:
        supporting: List[SourceRecord] = []
        contradicting: List[SourceRecord] = []
        primary_evidence: Optional[SourceRecord] = None

        # Filter out syndicated copies from independent evidence count
        independent_domains: Set[str] = set()

        # Keywords for matching claim semantics
        claim_keywords = set(re.findall(r"\w{4,}", claim.statement.lower()))

        for src in sources:
            src_text = f"{src.title} {src.snippet}".lower()
            match_count = sum(1 for kw in claim_keywords if kw in src_text)
            relevance = match_count / max(1, len(claim_keywords))

            if relevance > 0.25:
                # If this is not a duplicate syndicate
                if not src.syndication_group or src.syndication_group not in independent_domains:
                    independent_domains.add(src.domain)
                    supporting.append(src)
                    if src.is_primary:
                        primary_evidence = src

        # Check for contradictions
        conflicts = self.contradiction_detector.detect_conflicts(claim, sources)
        for conf in conflicts:
            for s in sources:
                if s.url == conf.second_source_url and s not in contradicting:
                    contradicting.append(s)

        # Check if source evidence is stale
        if any(s.is_stale for s in supporting) and not any(not s.is_stale for s in supporting):
            status = VerificationStatus.OUTDATED
            confidence = ConfidenceLevel.LOW
        elif conflicts:
            status = VerificationStatus.CONFLICTING
            confidence = ConfidenceLevel.UNCERTAIN
        elif primary_evidence and len(independent_domains) >= 1:
            status = VerificationStatus.VERIFIED
            confidence = ConfidenceLevel.HIGH
        elif len(independent_domains) >= 3:
            status = VerificationStatus.WELL_SUPPORTED
            confidence = ConfidenceLevel.HIGH
        elif len(independent_domains) == 2:
            status = VerificationStatus.PARTIALLY_SUPPORTED
            confidence = ConfidenceLevel.MEDIUM
        elif len(independent_domains) == 1:
            status = VerificationStatus.PARTIALLY_SUPPORTED
            confidence = ConfidenceLevel.LOW
        else:
            status = VerificationStatus.UNVERIFIED
            confidence = ConfidenceLevel.UNCERTAIN

        # Record citations for verified/supported claims
        for s in supporting:
            self.citation_manager.add_citation(claim.claim_id, s)

        return ClaimEvidenceMap(
            claim=claim,
            status=status,
            supporting_sources=supporting,
            contradicting_sources=contradicting,
            primary_evidence=primary_evidence,
            confidence=confidence,
            recency_note="Stale evidence detected" if status == VerificationStatus.OUTDATED else "Evidence active",
        )
