"""actions/research_engine.py — CHARLIE Research and Content Intelligence Tool Action.

Exposes deep research, fact verification, trend discovery, and content brief generation
directly to the assistant runtime and skills.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from engine.research.engine import InternetIntelligenceEngine
from engine.research.models import ResearchMode

_engine: Optional[InternetIntelligenceEngine] = None


def _get_engine() -> InternetIntelligenceEngine:
    global _engine
    if _engine is None:
        _engine = InternetIntelligenceEngine()
    return _engine


def research_engine(parameters: dict, **_unused) -> str:
    """Entry point action for deep research, trend discovery, and fact verification."""
    params = parameters or {}
    action = str(params.get("action") or "research").strip().lower()
    goal = str(params.get("goal") or params.get("query") or params.get("topic") or "").strip()
    mode_str = str(params.get("mode") or "STANDARD").strip().upper()
    niche = str(params.get("niche") or "technology").strip()
    region = str(params.get("region") or "GLOBAL").strip()
    claim = str(params.get("claim") or goal).strip()

    engine = _get_engine()

    try:
        if action in ("research", "execute_research", "quick_research", "execute_deep_research"):
            if not goal:
                return "Please provide a research goal or query."
            mode = ResearchMode.DEEP if ("deep" in action or mode_str == "DEEP") else (
                ResearchMode.QUICK if ("quick" in action or mode_str == "QUICK") else ResearchMode.STANDARD
            )
            report = engine.execute_research(goal, mode=mode)
            output = [
                f"### Research Report: {report.research_goal}",
                f"**Confidence**: {report.confidence.value} ({report.confidence_reason})",
                f"\n{report.summary}",
            ]
            if report.sources:
                output.append("\n**Sources Cited**:")
                for s in report.sources[:4]:
                    output.append(f"- [{s.domain}] {s.title} ({s.url})")
            return "\n".join(output)

        if action in ("verify_claim", "fact_check"):
            if not claim:
                return "Please provide a claim to verify."
            report = engine.execute_research(f"fact check {claim}", mode=ResearchMode.STANDARD)
            status = "VERIFIED / WELL SUPPORTED" if report.established_facts else (
                "CONFLICTING" if report.disagreements else "UNVERIFIED / MIXED"
            )
            lines = [
                f"### Fact Check Result: {status}",
                f"**Claim**: {claim}",
                f"**Confidence**: {report.confidence.value}",
                f"**Reason**: {report.confidence_reason}",
            ]
            if report.established_facts:
                lines.append("\n**Verified Facts**:")
                lines.extend(f"- {f}" for f in report.established_facts)
            if report.disagreements:
                lines.append("\n**Contradictions Found**:")
                lines.extend(f"- Discrepancy in {c.dimension}: {c.resolution_hint}" for c in report.disagreements)
            return "\n".join(lines)

        if action in ("discover_trends", "trends"):
            trends = engine.research_trends(niche=niche, region=region)
            if not trends:
                return f"No active trends found right now for {niche} ({region})."
            lines = [f"### Current Trends for {niche.title()} ({region}):\n"]
            for i, t in enumerate(trends[:5], 1):
                rumour_tag = " [RUMOUR/UNCONFIRMED]" if t.is_rumour else ""
                lines.append(f"{i}. **{t.topic}**{rumour_tag}")
                lines.append(f"   Summary: {t.summary}")
                lines.append(f"   Signals: {', '.join(t.signal_sources[:3])} | Cluster Size: {t.cluster_size}")
            return "\n".join(lines)

        if action in ("create_content_brief", "research_and_brief", "research_youtube_opportunity"):
            cand, brief, report = engine.research_youtube_topic(
                channel_context={"niche": niche, "region": region},
                preferred_niche=niche,
            )
            lines = [
                f"### YouTube Short Content Brief: {brief.topic}",
                f"**Target Audience**: {brief.target_audience}",
                f"**Main Angle**: {brief.main_angle}",
                f"\n**Hook Options**:",
            ]
            lines.extend(f"- {h}" for h in brief.hook_options)
            lines.append("\n**Verified Fact Lock**:")
            lines.extend(f"- [LOCKED] {f}" for f in brief.verified_facts[:3])
            if brief.claims_to_avoid:
                lines.append("\n**Claims to Avoid**:")
                lines.extend(f"- [AVOID] {c}" for c in brief.claims_to_avoid[:3])
            return "\n".join(lines)

        return f"Unknown research action: {action}"
    except Exception as e:
        return f"Research Engine error: {str(e)}"
