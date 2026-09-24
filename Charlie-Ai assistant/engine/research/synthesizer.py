"""engine/research/synthesizer.py — Structured Research Synthesizer."""

from __future__ import annotations

import time
from typing import List, Optional

from engine.research.models import (
    ClaimEvidenceMap,
    ConfidenceLevel,
    ContradictionRecord,
    ResearchPlan,
    ResearchReport,
    SourceRecord,
    VerificationStatus,
)


class ResearchSynthesizer:
    """Synthesizes verified claims, recent developments, and source evidence into a structured report."""

    def synthesize(
        self,
        plan: ResearchPlan,
        evidence_maps: List[ClaimEvidenceMap],
        sources: List[SourceRecord],
        conflicts: List[ContradictionRecord],
    ) -> ResearchReport:
        established_facts = []
        recent_developments = []
        source_claims = []
        uncertain_claims = []

        verified_count = 0
        primary_present = False

        for ev in evidence_maps:
            stmt = ev.claim.statement
            if ev.primary_evidence:
                primary_present = True

            if ev.status == VerificationStatus.VERIFIED:
                verified_count += 1
                if plan.time_sensitive:
                    recent_developments.append(stmt)
                else:
                    established_facts.append(stmt)
            elif ev.status == VerificationStatus.WELL_SUPPORTED:
                verified_count += 1
                if plan.time_sensitive:
                    recent_developments.append(stmt)
                else:
                    established_facts.append(stmt)
            elif ev.status == VerificationStatus.PARTIALLY_SUPPORTED:
                source_claims.append(stmt)
            elif ev.status in (VerificationStatus.UNVERIFIED, VerificationStatus.OUTDATED):
                uncertain_claims.append(f"{stmt} [{ev.status.value}]")

        # Determine overall confidence
        if conflicts:
            confidence = ConfidenceLevel.UNCERTAIN
            confidence_reason = f"{len(conflicts)} cross-source contradiction(s) detected; details require human review."
        elif primary_present and verified_count >= 1:
            confidence = ConfidenceLevel.HIGH
            confidence_reason = f"Confirmed by primary source ({sum(1 for s in sources if s.is_primary)} primary) and independent corroboration."
        elif verified_count >= 3:
            confidence = ConfidenceLevel.HIGH
            confidence_reason = f"Corroborated across multiple independent sources ({len(sources)} total sources)."
        elif verified_count >= 1 or len(source_claims) >= 2:
            confidence = ConfidenceLevel.MEDIUM
            confidence_reason = "Supported by secondary sources; cross-checking recommended for critical decisions."
        else:
            confidence = ConfidenceLevel.LOW
            confidence_reason = "Limited or unconfirmed evidence available."

        # Structured summary text
        summary_lines = [
            f"Research summary for goal: '{plan.goal}'",
            f"Time Context: {'Time-Sensitive Live Search' if plan.time_sensitive else 'Standard Knowledge'}",
            f"Confidence: {confidence.value} ({confidence_reason})",
        ]
        if recent_developments:
            summary_lines.append("\nRecent Developments:")
            summary_lines.extend(f"• {d}" for d in recent_developments[:4])
        if established_facts:
            summary_lines.append("\nEstablished Facts:")
            summary_lines.extend(f"• {f}" for f in established_facts[:4])
        if conflicts:
            summary_lines.append("\nConflicting Claims:")
            summary_lines.extend(f"• Discrepancy in {c.dimension}: {c.resolution_hint}" for c in conflicts[:3])

        summary_text = "\n".join(summary_lines)

        # Expiry timestamp
        expires_at = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(time.time() + plan.required_freshness_ttl_sec)
        )

        return ResearchReport(
            research_goal=plan.goal,
            time_context=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            summary=summary_text,
            established_facts=established_facts,
            recent_developments=recent_developments,
            source_claims=source_claims,
            disagreements=conflicts,
            uncertain_claims=uncertain_claims,
            sources=sources,
            citations=[],
            confidence=confidence,
            confidence_reason=confidence_reason,
            evidence_map=evidence_maps,
            next_actions=["Proceed to Content Strategy", "Generate Content Brief"] if "youtube" in plan.goal.lower() or "short" in plan.goal.lower() else ["Review findings"],
            expires_at=expires_at,
            is_reused_from_cache=False,
        )
