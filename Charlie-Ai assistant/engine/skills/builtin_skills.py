"""engine/skills/builtin_skills.py — Standard Modular Starter Skills for JARVIS.

Provides foundational and advanced procedural skills out-of-the-box across Windows, Files,
Spreadsheet, YouTube/Video, Coding, Antigravity, and Research.
"""

from __future__ import annotations

from typing import List

from engine.skills.models import (
    Skill,
    SkillCategory,
    SkillStatus,
    SkillStep,
    SkillTrigger,
    SkillVariable,
)


def get_builtin_skills() -> List[Skill]:
    """Returns the 12 core modular built-in starter skills."""
    skills = []

    # 1. OpenApplication
    skills.append(
        Skill(
            id="skill_builtin_open_app",
            name="OpenApplication",
            description="Launch or focus a Windows desktop application safely.",
            intent="open desktop application",
            category=SkillCategory.WINDOWS,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("open application"),
                SkillTrigger("launch app"),
                SkillTrigger("app kholo"),
            ],
            variables=[
                SkillVariable("app_name", "string", default="", description="Application executable or name", required=True),
            ],
            steps=[
                SkillStep(
                    id="step_1",
                    name="Launch Process",
                    action="launch_process",
                    adapter="WindowsAdapter",
                    tool="system_launch",
                    inputs={"app_name": "{app_name}"},
                )
            ],
            required_agents=["GeneralAgent"],
            required_permissions=["SAFE_EXECUTE"],
            preconditions=["Application is installed or accessible on PATH"],
            verification_rules=["Process running in task list"],
            confidence=0.95,
            source="builtin",
        )
    )

    # 2. FindRecentFile
    skills.append(
        Skill(
            id="skill_builtin_find_recent_file",
            name="FindRecentFile",
            description="Locate recently modified files matching pattern.",
            intent="find recent file",
            category=SkillCategory.FILES,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("find recent file"),
                SkillTrigger("file dhundho"),
                SkillTrigger("locate file"),
            ],
            variables=[
                SkillVariable("filename_pattern", "string", default="*", description="File pattern", required=True),
                SkillVariable("search_dir", "dir_path", default=".", description="Starting directory", required=False),
            ],
            steps=[
                SkillStep(
                    id="step_1",
                    name="Scan Filesystem",
                    action="search_filesystem",
                    adapter="FileSystemAdapter",
                    tool="file_search",
                    inputs={"pattern": "{filename_pattern}", "root": "{search_dir}"},
                )
            ],
            required_agents=["FileAgent"],
            required_permissions=["FILE_READ"],
            preconditions=["Directory readable"],
            verification_rules=["At least zero or more matching files returned"],
            confidence=0.95,
            source="builtin",
        )
    )

    # 3. RunProject
    skills.append(
        Skill(
            id="skill_builtin_run_project",
            name="RunProject",
            description="Detect project tech stack and launch development services safely.",
            intent="run project development server",
            category=SkillCategory.CODING,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("run project"),
                SkillTrigger("project start karo"),
                SkillTrigger("launch dev server"),
            ],
            variables=[
                SkillVariable("project_dir", "dir_path", default=".", description="Root project directory", required=True),
                SkillVariable("command", "string", default="", description="Explicit start command (optional)", required=False),
            ],
            steps=[
                SkillStep(
                    id="step_1",
                    name="Detect Stack",
                    action="inspect_project",
                    adapter="CodingAdapter",
                    tool="code_inspect",
                    inputs={"project_dir": "{project_dir}"},
                ),
                SkillStep(
                    id="step_2",
                    name="Execute Run Command",
                    action="run_command",
                    adapter="PowerShellAdapter",
                    tool="cli_exec",
                    inputs={"cwd": "{project_dir}", "command": "{command}"},
                    dependencies=["step_1"],
                ),
            ],
            required_agents=["CodingAgent"],
            required_permissions=["SAFE_EXECUTE", "FILE_READ"],
            preconditions=["Project folder exists", "Required runtime installed"],
            verification_rules=["Server listening or process active without exit error"],
            confidence=0.9,
            source="builtin",
        )
    )

    # 4. ResearchTopic
    skills.append(
        Skill(
            id="skill_builtin_research_topic",
            name="ResearchTopic",
            description="Search web sources and generate a synthesized research brief.",
            intent="research topic on web",
            category=SkillCategory.RESEARCH,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("research topic"),
                SkillTrigger("topic par research karo"),
                SkillTrigger("find info on web"),
            ],
            variables=[
                SkillVariable("query", "string", default="", description="Research query", required=True),
                SkillVariable("depth", "string", default="standard", description="Search depth", choices=["quick", "standard", "deep"]),
            ],
            steps=[
                SkillStep(
                    id="step_1",
                    name="Web Search",
                    action="search_web",
                    adapter="BrowserAdapter",
                    tool="web_search",
                    inputs={"query": "{query}"},
                ),
                SkillStep(
                    id="step_2",
                    name="Synthesize Research Brief",
                    action="synthesize_summary",
                    adapter="ResearchAdapter",
                    inputs={"topic": "{query}"},
                    dependencies=["step_1"],
                ),
            ],
            required_agents=["ResearchAgent"],
            required_permissions=["NETWORK_ACCESS"],
            preconditions=["Internet access available"],
            verification_rules=["Brief contains cited facts and non-empty summary"],
            confidence=0.9,
            source="builtin",
        )
    )

    # 5. CreateYouTubeShort
    skills.append(
        Skill(
            id="skill_builtin_create_youtube_short",
            name="CreateYouTubeShort",
            description="End-to-end vertical 9:16 short video generation from topic or trend.",
            intent="create youtube short video",
            category=SkillCategory.YOUTUBE,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("short bana do"),
                SkillTrigger("youtube short create karo"),
                SkillTrigger("aaj ka short ready karo"),
                SkillTrigger("reel bana do"),
                SkillTrigger("new short"),
            ],
            variables=[
                SkillVariable("topic", "string", default="Trending Tech", description="Video topic", required=False),
                SkillVariable("duration", "integer", default=60, description="Target duration in seconds", required=False),
                SkillVariable("output_dir", "dir_path", default="exports/shorts", description="Output directory", required=False),
            ],
            steps=[
                SkillStep(
                    id="step_1",
                    name="Research Trend & Hook",
                    action="research_trend",
                    adapter="VideoAdapter",
                    inputs={"topic": "{topic}"},
                ),
                SkillStep(
                    id="step_2",
                    name="Write Script",
                    action="write_script",
                    adapter="VideoAdapter",
                    inputs={"duration": "{duration}"},
                    dependencies=["step_1"],
                ),
                SkillStep(
                    id="step_3",
                    name="Assemble 9:16 Video",
                    action="render_timeline",
                    adapter="VideoEditorAdapter",
                    inputs={"aspect_ratio": "9:16"},
                    dependencies=["step_2"],
                ),
                SkillStep(
                    id="step_4",
                    name="Add Animated Captions",
                    action="burn_subtitles",
                    adapter="VideoEditorAdapter",
                    dependencies=["step_3"],
                ),
                SkillStep(
                    id="step_5",
                    name="Export Final Video",
                    action="export_project",
                    adapter="VideoEditorAdapter",
                    inputs={"output_dir": "{output_dir}"},
                    dependencies=["step_4"],
                    verification_rule="video_output",
                ),
            ],
            required_agents=["VideoAgent"],
            required_permissions=["FILE_READ", "FILE_WRITE", "MEDIA_PROCESS"],
            preconditions=["FFmpeg installed on PATH", "Output directory writable"],
            verification_rules=[
                "Output video file exists",
                "Resolution matches 1080x1920 (9:16)",
                "Audio stream present",
            ],
            confidence=0.88,
            source="builtin",
        )
    )

    # 6. CleanExcelWorkbook
    skills.append(
        Skill(
            id="skill_builtin_clean_excel",
            name="CleanExcelWorkbook",
            description="Normalize spreadsheet column headers, datatypes, and trim trailing whitespace.",
            intent="clean and normalize excel workbook",
            category=SkillCategory.SPREADSHEET,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("clean excel workbook"),
                SkillTrigger("excel clean karo"),
                SkillTrigger("sheet format karo"),
            ],
            variables=[
                SkillVariable("INPUT_WORKBOOK", "file_path", default="", description="Target Excel workbook", required=True),
                SkillVariable("OUTPUT_PATH", "file_path", default="cleaned_workbook.xlsx", description="Cleaned output path", required=False),
            ],
            steps=[
                SkillStep(
                    id="step_1",
                    name="Inspect Workbook",
                    action="inspect_workbook",
                    adapter="ExcelAdapter",
                    inputs={"path": "{INPUT_WORKBOOK}"},
                ),
                SkillStep(
                    id="step_2",
                    name="Normalize Data",
                    action="clean_workbook",
                    adapter="ExcelAdapter",
                    inputs={"path": "{INPUT_WORKBOOK}", "output": "{OUTPUT_PATH}"},
                    dependencies=["step_1"],
                    verification_rule="excel_integrity",
                ),
            ],
            required_agents=["SpreadsheetAgent"],
            required_permissions=["FILE_READ", "FILE_WRITE"],
            preconditions=["openpyxl installed", "Input file exists"],
            verification_rules=["Workbook loads cleanly without corruption"],
            confidence=0.92,
            source="builtin",
        )
    )

    # 7. CreateExcelReport
    skills.append(
        Skill(
            id="skill_builtin_create_excel_report",
            name="CreateExcelReport",
            description="Extract monthly data, compute totals, generate professional summary sheet.",
            intent="generate monthly excel report",
            category=SkillCategory.SPREADSHEET,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("monthly excel report"),
                SkillTrigger("monthly report bana do"),
                SkillTrigger("sales report banao"),
                SkillTrigger("generate spreadsheet report"),
            ],
            variables=[
                SkillVariable("INPUT_WORKBOOK", "file_path", default="", description="Input Excel file", required=True),
                SkillVariable("REPORT_MONTH", "string", default="September", description="Target reporting month", required=False),
                SkillVariable("OUTPUT_PATH", "file_path", default="Monthly_Report.xlsx", description="Output report file", required=False),
            ],
            steps=[
                SkillStep(
                    id="step_1",
                    name="Inspect Workbook Structure",
                    action="inspect_workbook",
                    adapter="ExcelAdapter",
                    inputs={"path": "{INPUT_WORKBOOK}"},
                ),
                SkillStep(
                    id="step_2",
                    name="Calculate Totals & Build Summary",
                    action="create_summary_sheet",
                    adapter="ExcelAdapter",
                    inputs={
                        "path": "{INPUT_WORKBOOK}",
                        "month": "{REPORT_MONTH}",
                        "output": "{OUTPUT_PATH}",
                    },
                    dependencies=["step_1"],
                    verification_rule="excel_integrity",
                ),
            ],
            required_agents=["SpreadsheetAgent"],
            required_permissions=["FILE_READ", "FILE_WRITE"],
            preconditions=["openpyxl installed", "Input file exists"],
            verification_rules=[
                "Workbook loads cleanly without corruption",
                "Summary calculations non-empty",
                "Formulas intact",
            ],
            confidence=0.92,
            source="builtin",
        )
    )

    # 8. OpenAntigravityProject
    skills.append(
        Skill(
            id="skill_builtin_open_antigravity_project",
            name="OpenAntigravityProject",
            description="Focus or open Antigravity IDE workspace for current codebase.",
            intent="open project in antigravity ide",
            category=SkillCategory.ANTIGRAVITY,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("open antigravity project"),
                SkillTrigger("antigravity kholo"),
                SkillTrigger("open in antigravity"),
            ],
            variables=[
                SkillVariable("project_path", "dir_path", default=".", description="Workspace path", required=False),
            ],
            steps=[
                SkillStep(
                    id="step_1",
                    name="Focus or Launch Antigravity",
                    action="find_antigravity_window",
                    adapter="AntigravityAdapter",
                    inputs={"workspace": "{project_path}"},
                )
            ],
            required_agents=["AntigravityAgent"],
            required_permissions=["SAFE_EXECUTE"],
            preconditions=["Antigravity process or shortcut available"],
            verification_rules=["Antigravity window active or launched"],
            confidence=0.95,
            source="builtin",
        )
    )

    # 9. ContinueCodingProject
    skills.append(
        Skill(
            id="skill_builtin_continue_coding_project",
            name="ContinueCodingProject",
            description="Inspect git branch status, inspect codebase, and apply targeted implementation.",
            intent="continue coding implementation in project",
            category=SkillCategory.CODING,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("continue coding project"),
                SkillTrigger("code aage badhao"),
                SkillTrigger("implement next phase"),
            ],
            variables=[
                SkillVariable("project_path", "dir_path", default=".", description="Project directory", required=False),
                SkillVariable("task_description", "string", default="", description="Pending task instructions", required=True),
            ],
            steps=[
                SkillStep(
                    id="step_1",
                    name="Inspect Codebase",
                    action="inspect_project",
                    adapter="CodingAdapter",
                    inputs={"project_dir": "{project_path}"},
                ),
                SkillStep(
                    id="step_2",
                    name="Apply Code Changes",
                    action="apply_targeted_fix",
                    adapter="CodingAdapter",
                    inputs={"task": "{task_description}"},
                    dependencies=["step_1"],
                ),
            ],
            required_agents=["CodingAgent"],
            required_permissions=["FILE_READ", "FILE_WRITE"],
            preconditions=["Git repository available"],
            verification_rules=["Syntax valid", "Target files modified"],
            confidence=0.9,
            source="builtin",
        )
    )

    # 10. DiagnoseDevelopmentError
    skills.append(
        Skill(
            id="skill_builtin_diagnose_error",
            name="DiagnoseDevelopmentError",
            description="Analyze stack trace, parse error log, locate offending file and line.",
            intent="diagnose build or runtime error",
            category=SkillCategory.CODING,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("diagnose error"),
                SkillTrigger("error check karo"),
                SkillTrigger("debug build failure"),
            ],
            variables=[
                SkillVariable("error_log", "string", default="", description="Error trace or message", required=True),
                SkillVariable("project_dir", "dir_path", default=".", description="Project root", required=False),
            ],
            steps=[
                SkillStep(
                    id="step_1",
                    name="Analyze Trace & Diagnose",
                    action="inspect_project",
                    adapter="CodingAdapter",
                    inputs={"error": "{error_log}", "dir": "{project_dir}"},
                )
            ],
            required_agents=["CodingAgent"],
            required_permissions=["FILE_READ"],
            preconditions=["Project files readable"],
            verification_rules=["Diagnosis report provides root cause and fix recommendation"],
            confidence=0.92,
            source="builtin",
        )
    )

    # 11. CreateBackup
    skills.append(
        Skill(
            id="skill_builtin_create_backup",
            name="CreateBackup",
            description="Create a zip archive backup of target directory or files.",
            intent="create file or project backup",
            category=SkillCategory.FILES,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("create backup"),
                SkillTrigger("backup banao"),
                SkillTrigger("backup files"),
            ],
            variables=[
                SkillVariable("source_path", "dir_path", default=".", description="Source directory", required=True),
                SkillVariable("backup_dest", "file_path", default="backup.zip", description="Destination archive path", required=False),
            ],
            steps=[
                SkillStep(
                    id="step_1",
                    name="Archive Files",
                    action="create_backup",
                    adapter="FileSystemAdapter",
                    tool="file_backup",
                    inputs={"source": "{source_path}", "dest": "{backup_dest}"},
                    verification_rule="file_exists",
                )
            ],
            required_agents=["FileAgent"],
            required_permissions=["FILE_READ", "FILE_WRITE"],
            preconditions=["Source path exists", "Destination folder writable"],
            verification_rules=["Archive file exists and size > 0"],
            confidence=0.96,
            source="builtin",
        )
    )

    # 12. VerifyGeneratedFile
    skills.append(
        Skill(
            id="skill_builtin_verify_generated_file",
            name="VerifyGeneratedFile",
            description="Run integrity and domain verification on newly generated artifacts.",
            intent="verify generated output file",
            category=SkillCategory.AUTOMATION,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("verify generated file"),
                SkillTrigger("file verify karo"),
                SkillTrigger("check output integrity"),
            ],
            variables=[
                SkillVariable("file_path", "file_path", default="", description="Target file path", required=True),
                SkillVariable("expected_type", "string", default="auto", description="Expected file type", required=False),
            ],
            steps=[
                SkillStep(
                    id="step_1",
                    name="Verify Integrity",
                    action="verify_file",
                    adapter="VerificationAdapter",
                    tool="verify_artifact",
                    inputs={"path": "{file_path}", "type": "{expected_type}"},
                )
            ],
            required_agents=["VerificationEngine"],
            required_permissions=["FILE_READ"],
            preconditions=["File path specified"],
            verification_rules=["File readable and meets type criteria"],
            confidence=0.98,
            source="builtin",
        )
    )

    # 13. FullProjectAudit
    skills.append(
        Skill(
            id="skill_builtin_full_project_audit",
            name="FullProjectAudit",
            description="Inspect a project, identify defects and security risks, run available checks, and produce a prioritized audit.",
            intent="perform a full project code and security audit",
            category=SkillCategory.CODING,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("full project audit"),
                SkillTrigger("audit my codebase"),
                SkillTrigger("project ki complete checking karo"),
            ],
            variables=[
                SkillVariable("project_path", "dir_path", default=".", description="Project root", required=True),
                SkillVariable("focus", "string", default="all", description="Audit focus: all, security, tests, or architecture"),
            ],
            steps=[
                SkillStep(id="step_1", name="Map Project", action="inspect_project", adapter="CodingAdapter", tool="code_inspect", inputs={"project_path": "{project_path}"}),
                SkillStep(id="step_2", name="Review Security Boundaries", action="security_review", adapter="SecurityAdapter", tool="security_audit", inputs={"project_path": "{project_path}", "focus": "{focus}"}, dependencies=["step_1"]),
                SkillStep(id="step_3", name="Run Tests and Checks", action="run_verification", adapter="VerificationAdapter", tool="verify_project", inputs={"project_path": "{project_path}"}, dependencies=["step_2"]),
                SkillStep(id="step_4", name="Write Prioritized Report", action="create_audit_report", adapter="ReportAdapter", inputs={"project_path": "{project_path}"}, dependencies=["step_3"], verification_rule="report_exists"),
            ],
            required_agents=["CodingAgent", "SecurityAgent", "VerificationAgent"],
            required_permissions=["FILE_READ", "SAFE_EXECUTE"],
            preconditions=["Project folder exists", "Source files are readable"],
            verification_rules=["Report contains findings, evidence, severity, and recommended fixes", "Tests and skipped checks are clearly separated"],
            confidence=0.94,
            source="builtin",
        )
    )

    # 14. BuildReleaseCandidate
    skills.append(
        Skill(
            id="skill_builtin_build_release_candidate",
            name="BuildReleaseCandidate",
            description="Prepare a release candidate with a backup, dependency check, tests, packaging, and artifact verification.",
            intent="build and verify a release candidate",
            category=SkillCategory.CODING,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[SkillTrigger("build release candidate"), SkillTrigger("prepare production build"), SkillTrigger("release build ready karo")],
            variables=[
                SkillVariable("project_path", "dir_path", default=".", description="Project root", required=True),
                SkillVariable("output_path", "dir_path", default="dist", description="Release output directory"),
            ],
            steps=[
                SkillStep(id="step_1", name="Create Source Backup", action="create_backup", adapter="FileSystemAdapter", tool="file_backup", inputs={"source": "{project_path}"}),
                SkillStep(id="step_2", name="Inspect Release Configuration", action="inspect_project", adapter="CodingAdapter", tool="code_inspect", inputs={"project_path": "{project_path}"}, dependencies=["step_1"]),
                SkillStep(id="step_3", name="Run Tests", action="run_tests", adapter="VerificationAdapter", tool="verify_project", inputs={"project_path": "{project_path}"}, dependencies=["step_2"]),
                SkillStep(id="step_4", name="Package Application", action="build_release", adapter="BuildAdapter", tool="package_project", inputs={"project_path": "{project_path}", "output_path": "{output_path}"}, dependencies=["step_3"]),
                SkillStep(id="step_5", name="Verify Release Artifact", action="verify_file", adapter="VerificationAdapter", tool="verify_artifact", inputs={"path": "{output_path}"}, dependencies=["step_4"]),
            ],
            required_agents=["CodingAgent", "VerificationAgent"],
            required_permissions=["FILE_READ", "FILE_WRITE", "SAFE_EXECUTE"],
            preconditions=["Project folder exists", "Build toolchain is installed", "Output folder is writable"],
            verification_rules=["Backup exists", "Tests pass or are explicitly reported", "Release artifact exists and launches"],
            recovery_rules=["Never overwrite an existing release without confirmation", "Keep the source backup if packaging fails"],
            confidence=0.93,
            source="builtin",
        )
    )

    # 15. ResearchToDecisionReport
    skills.append(
        Skill(
            id="skill_builtin_research_to_decision_report",
            name="ResearchToDecisionReport",
            description="Research a difficult question, compare credible sources, identify uncertainty, and produce an actionable decision report.",
            intent="research a complex topic and create a decision report",
            category=SkillCategory.RESEARCH,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[SkillTrigger("deep research report"), SkillTrigger("compare options and recommend"), SkillTrigger("decision report banao")],
            variables=[
                SkillVariable("question", "string", default="", description="Question or decision to investigate", required=True),
                SkillVariable("options", "string", default="", description="Options to compare, if applicable"),
                SkillVariable("output_path", "file_path", default="research_decision_report.md", description="Report destination"),
            ],
            steps=[
                SkillStep(id="step_1", name="Frame the Decision", action="define_criteria", adapter="ResearchAdapter", inputs={"question": "{question}", "options": "{options}"}),
                SkillStep(id="step_2", name="Gather Sources", action="search_web", adapter="BrowserAdapter", tool="web_search", inputs={"query": "{question}"}, dependencies=["step_1"]),
                SkillStep(id="step_3", name="Cross-check Evidence", action="verify_sources", adapter="ResearchAdapter", inputs={"question": "{question}"}, dependencies=["step_2"]),
                SkillStep(id="step_4", name="Write Decision Report", action="write_report", adapter="ReportAdapter", inputs={"question": "{question}", "output_path": "{output_path}"}, dependencies=["step_3"], verification_rule="report_exists"),
            ],
            required_agents=["ResearchAgent", "VerificationAgent"],
            required_permissions=["NETWORK_ACCESS", "FILE_WRITE"],
            preconditions=["Internet access available", "Question is specific enough to research"],
            verification_rules=["Sources are cited", "Facts and recommendations are separated", "Uncertainty and assumptions are disclosed"],
            confidence=0.94,
            source="builtin",
        )
    )

    # ── Phase 5 Deep Research & Content Intelligence Skills ─────────────────

    # 16. QuickWebResearch
    skills.append(
        Skill(
            id="skill_builtin_quick_web_research",
            name="QuickWebResearch",
            description="Fast targeted web lookup with date validation and source citations.",
            intent="quick research on web",
            category=SkillCategory.RESEARCH,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("quick research"),
                SkillTrigger("jaldi search karo"),
                SkillTrigger("fast web lookup"),
            ],
            variables=[
                SkillVariable("query", "string", default="", description="Research query", required=True),
            ],
            steps=[
                SkillStep(id="step_1", name="Quick Search & Verify", action="quick_research", adapter="ResearchAdapter", tool="research_engine", inputs={"goal": "{query}", "mode": "QUICK"}),
            ],
            required_agents=["ResearchAgent"],
            required_permissions=["NETWORK_ACCESS"],
            preconditions=["Internet access available"],
            verification_rules=["Returns concise answer with cited source and recency check"],
            confidence=0.95,
            source="builtin",
        )
    )

    # 17. DeepResearch
    skills.append(
        Skill(
            id="skill_builtin_deep_research",
            name="DeepResearch",
            description="Multi-query deep investigation, claim extraction, contradiction detection, and comprehensive report.",
            intent="deep comprehensive research report",
            category=SkillCategory.RESEARCH,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("deep research karo"),
                SkillTrigger("in depth research"),
                SkillTrigger("comprehensive investigation"),
            ],
            variables=[
                SkillVariable("topic", "string", default="", description="Topic for deep research", required=True),
            ],
            steps=[
                SkillStep(id="step_1", name="Deep Research Execution", action="execute_deep_research", adapter="ResearchAdapter", tool="research_engine", inputs={"goal": "{topic}", "mode": "DEEP"}),
            ],
            required_agents=["ResearchAgent", "VerificationAgent"],
            required_permissions=["NETWORK_ACCESS"],
            preconditions=["Topic provided"],
            verification_rules=["Report separates established facts, recent developments, and uncertainties"],
            confidence=0.93,
            source="builtin",
        )
    )

    # 18. FactCheck
    skills.append(
        Skill(
            id="skill_builtin_fact_check",
            name="FactCheck",
            description="Verify factual claims against primary sources and independent evidence.",
            intent="fact check claim or statement",
            category=SkillCategory.RESEARCH,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("ye sach hai kya"),
                SkillTrigger("fact check"),
                SkillTrigger("verify claim"),
                SkillTrigger("is this news real"),
            ],
            variables=[
                SkillVariable("claim", "string", default="", description="Claim or statement to verify", required=True),
            ],
            steps=[
                SkillStep(id="step_1", name="Cross-Check Claim", action="verify_claim", adapter="ResearchAdapter", tool="research_engine", inputs={"claim": "{claim}"}),
            ],
            required_agents=["ResearchAgent"],
            required_permissions=["NETWORK_ACCESS"],
            preconditions=["Claim text provided"],
            verification_rules=["Returns confidence status and lists supporting or contradicting evidence"],
            confidence=0.95,
            source="builtin",
        )
    )

    # 19. CurrentTrendResearch
    skills.append(
        Skill(
            id="skill_builtin_current_trend_research",
            name="CurrentTrendResearch",
            description="Discover current momentum topics, cluster headlines, and filter stale news.",
            intent="find current trends",
            category=SkillCategory.RESEARCH,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("aaj kya trend kar raha hai"),
                SkillTrigger("today trending tech"),
                SkillTrigger("current trends"),
                SkillTrigger("whats trending"),
            ],
            variables=[
                SkillVariable("niche", "string", default="technology", description="Industry or topic niche"),
                SkillVariable("region", "string", default="GLOBAL", description="Geographical scope: GLOBAL or INDIA"),
            ],
            steps=[
                SkillStep(id="step_1", name="Scan & Cluster Trends", action="discover_trends", adapter="ResearchAdapter", tool="research_engine", inputs={"niche": "{niche}", "region": "{region}"}),
            ],
            required_agents=["ResearchAgent"],
            required_permissions=["NETWORK_ACCESS"],
            preconditions=["Internet access available"],
            verification_rules=["Returns clustered fresh topics with momentum signals"],
            confidence=0.92,
            source="builtin",
        )
    )

    # 20. ResearchSoftwareDocs
    skills.append(
        Skill(
            id="skill_builtin_research_software_docs",
            name="ResearchSoftwareDocs",
            description="Research official framework/SDK documentation, release notes, and version compatibility.",
            intent="research software documentation and version",
            category=SkillCategory.CODING,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("research official docs"),
                SkillTrigger("check library documentation"),
                SkillTrigger("latest flutter version docs"),
            ],
            variables=[
                SkillVariable("library_or_tool", "string", default="", description="Package or tool name", required=True),
                SkillVariable("version", "string", default="", description="Target version (optional)"),
            ],
            steps=[
                SkillStep(id="step_1", name="Fetch Official Docs", action="research_docs", adapter="CodingAdapter", tool="research_engine", inputs={"tool": "{library_or_tool}", "version": "{version}"}),
            ],
            required_agents=["CodingAgent", "ResearchAgent"],
            required_permissions=["NETWORK_ACCESS"],
            preconditions=["Library name specified"],
            verification_rules=["Prioritizes primary domains and official changelogs"],
            confidence=0.94,
            source="builtin",
        )
    )

    # 21. ResearchYouTubeTopic
    skills.append(
        Skill(
            id="skill_builtin_research_youtube_topic",
            name="ResearchYouTubeTopic",
            description="Find best YouTube video/Short topic using channel memory, trends, and opportunity scoring.",
            intent="research youtube topic for channel",
            category=SkillCategory.YOUTUBE,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("channel ke liye best topic find karo"),
                SkillTrigger("youtube topic research"),
                SkillTrigger("suggest short idea"),
            ],
            variables=[
                SkillVariable("channel_niche", "string", default="technology", description="Channel content niche"),
                SkillVariable("format", "string", default="Short", description="Short or Long-form"),
            ],
            steps=[
                SkillStep(id="step_1", name="Evaluate Content Opportunity", action="research_youtube_opportunity", adapter="VideoAdapter", tool="research_engine", inputs={"niche": "{channel_niche}", "format": "{format}"}),
            ],
            required_agents=["ResearchAgent", "VideoAgent"],
            required_permissions=["NETWORK_ACCESS"],
            preconditions=["Channel context accessible"],
            verification_rules=["Returns scored candidate topic with freshness and audience match"],
            confidence=0.92,
            source="builtin",
        )
    )

    # 22. CreateContentBrief
    skills.append(
        Skill(
            id="skill_builtin_create_content_brief",
            name="CreateContentBrief",
            description="Generate verified ContentBrief and FactLock for video or script production.",
            intent="create video content brief with fact lock",
            category=SkillCategory.YOUTUBE,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("content brief ready karo"),
                SkillTrigger("generate script brief"),
                SkillTrigger("video brief with fact lock"),
            ],
            variables=[
                SkillVariable("topic", "string", default="", description="Video topic", required=True),
                SkillVariable("target_duration", "integer", default=60, description="Duration in seconds"),
            ],
            steps=[
                SkillStep(id="step_1", name="Generate Brief & Lock Facts", action="create_content_brief", adapter="VideoAdapter", tool="research_engine", inputs={"topic": "{topic}", "duration": "{target_duration}"}),
            ],
            required_agents=["VideoAgent", "ResearchAgent"],
            required_permissions=["NETWORK_ACCESS"],
            preconditions=["Topic specified"],
            verification_rules=["Brief contains hook options, verified facts, and claims to avoid"],
            confidence=0.94,
            source="builtin",
        )
    )

    # 23. ResearchToExcel
    skills.append(
        Skill(
            id="skill_builtin_research_to_excel",
            name="ResearchToExcel",
            description="Research topic, collect structured facts and comparisons, and export to Excel workbook.",
            intent="research topic and export to excel",
            category=SkillCategory.SPREADSHEET,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("research karke excel report bana do"),
                SkillTrigger("export research to spreadsheet"),
                SkillTrigger("compare and put in excel"),
            ],
            variables=[
                SkillVariable("query", "string", default="", description="Comparison or research query", required=True),
                SkillVariable("output_path", "file_path", default="research_comparison.xlsx", description="Output workbook path"),
            ],
            steps=[
                SkillStep(id="step_1", name="Conduct Research", action="execute_research", adapter="ResearchAdapter", tool="research_engine", inputs={"goal": "{query}"}),
                SkillStep(id="step_2", name="Export to Excel", action="export_research_excel", adapter="ExcelAdapter", tool="research_engine", inputs={"output": "{output_path}"}, dependencies=["step_1"]),
            ],
            required_agents=["ResearchAgent", "SpreadsheetAgent"],
            required_permissions=["NETWORK_ACCESS", "FILE_WRITE"],
            preconditions=["openpyxl installed", "Output folder writable"],
            verification_rules=["Excel workbook created with categorized rows and citations"],
            confidence=0.93,
            source="builtin",
        )
    )

    # 24. ResearchToShort
    skills.append(
        Skill(
            id="skill_builtin_research_to_short",
            name="ResearchToShort",
            description="Autonomous pipeline: research current trend, lock facts, create brief, and produce 9:16 Short.",
            intent="research trend and make youtube short",
            category=SkillCategory.YOUTUBE,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("aaj ke trend par short bana do"),
                SkillTrigger("research karke short ready karo"),
                SkillTrigger("research to short"),
            ],
            variables=[
                SkillVariable("niche", "string", default="technology", description="Content niche"),
                SkillVariable("duration", "integer", default=60, description="Video length in seconds"),
            ],
            steps=[
                SkillStep(id="step_1", name="Research Trend & Brief", action="research_and_brief", adapter="ResearchAdapter", tool="research_engine", inputs={"niche": "{niche}"}),
                SkillStep(id="step_2", name="Create YouTube Short", action="create_short", adapter="VideoAdapter", tool="manage_skills", inputs={"skill_id": "skill_builtin_create_youtube_short"}, dependencies=["step_1"]),
            ],
            required_agents=["ResearchAgent", "VideoAgent"],
            required_permissions=["NETWORK_ACCESS", "FILE_WRITE", "MEDIA_PROCESS"],
            preconditions=["FFmpeg installed", "Internet access available"],
            verification_rules=["Output video exists, resolution 1080x1920, facts verified"],
            confidence=0.91,
            source="builtin",
        )
    )

    # 25. MonitorTopic
    skills.append(
        Skill(
            id="skill_builtin_monitor_topic",
            name="MonitorTopic",
            description="Track topic updates over time and report new developments or changed facts.",
            intent="monitor topic for updates",
            category=SkillCategory.RESEARCH,
            status=SkillStatus.TRUSTED,
            version=1,
            triggers=[
                SkillTrigger("monitor topic"),
                SkillTrigger("track updates"),
                SkillTrigger("is topic ko monitor karo"),
            ],
            variables=[
                SkillVariable("topic", "string", default="", description="Topic or company to monitor", required=True),
            ],
            steps=[
                SkillStep(id="step_1", name="Inspect Changes", action="watch_topic", adapter="ResearchAdapter", tool="research_engine", inputs={"topic": "{topic}"}),
            ],
            required_agents=["ResearchAgent"],
            required_permissions=["NETWORK_ACCESS"],
            preconditions=["Topic specified"],
            verification_rules=["Highlights new sources and changes compared to prior state"],
            confidence=0.93,
            source="builtin",
        )
    )

    return skills
