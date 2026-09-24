"""engine/research/bridge.py — Research-to-Action Bridge for Skills, Video, Excel, Coding, and Antigravity."""

from __future__ import annotations

from typing import Any, Dict, Optional

from engine.research.models import ContentBrief, ResearchReport


class ResearchToActionBridge:
    """Connects research and content intelligence directly to downstream skills and specialized agents."""

    @staticmethod
    def bridge_to_youtube_short(
        brief: ContentBrief,
        output_dir: str = "exports/shorts",
    ) -> Dict[str, Any]:
        """Prepares parameterized inputs for the Phase 4 'CreateYouTubeShort' skill."""
        return {
            "skill_id": "skill_builtin_create_youtube_short",
            "skill_name": "CreateYouTubeShort",
            "inputs": {
                "topic": brief.topic,
                "duration": brief.target_duration,
                "output_dir": output_dir,
            },
            "context": {
                "main_angle": brief.main_angle,
                "hook": brief.hook_options[0] if brief.hook_options else "",
                "verified_facts": brief.verified_facts,
                "claims_to_avoid": brief.claims_to_avoid,
                "fact_lock": brief.fact_lock,
            },
            "status": "ready_for_handoff",
        }

    @staticmethod
    def bridge_to_excel_report(
        report: ResearchReport,
        output_path: str = "research_report.xlsx",
    ) -> Dict[str, Any]:
        """Prepares structured findings for 'CreateExcelReport' or SpreadsheetAgent."""
        rows = []
        for f in report.established_facts:
            rows.append({"Category": "Established Fact", "Detail": f, "Confidence": report.confidence.value})
        for d in report.recent_developments:
            rows.append({"Category": "Recent Development", "Detail": d, "Confidence": report.confidence.value})
        for c in report.disagreements:
            rows.append({"Category": "Disagreement", "Detail": f"{c.dimension}: {c.first_value} vs {c.second_value}", "Confidence": "UNCERTAIN"})

        return {
            "skill_id": "skill_builtin_create_excel_report",
            "skill_name": "CreateExcelReport",
            "inputs": {
                "OUTPUT_PATH": output_path,
                "REPORT_MONTH": "Current",
            },
            "dataset": rows,
            "status": "ready_for_handoff",
        }

    @staticmethod
    def bridge_to_coding_or_antigravity(
        report: ResearchReport,
        target_project_path: str = ".",
    ) -> Dict[str, Any]:
        """Prepares technical release/documentation findings for CodingAgent or AntigravityAgent."""
        return {
            "agent": "AntigravityAgent",
            "task_type": "CODE_OR_DOCS_UPDATE",
            "target_path": target_project_path,
            "verified_requirements": report.established_facts + report.recent_developments,
            "uncertainties": report.uncertain_claims,
            "sources": [s.url for s in report.sources if s.url],
            "status": "ready_for_handoff",
        }
