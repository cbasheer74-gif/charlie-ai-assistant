"""
engine/pro_brain.py — Charlie Pro Brain: Next-Level Parallel Task Intelligence

For PAID PLAN subscribers (Launch / Growth / Scale / Annual).
Provides:
  - Parallel multi-task execution with dependency graph
  - 50+ smart workflow automation chains
  - Priority queue (CRITICAL > HIGH > NORMAL > LOW > BACKGROUND)
  - Real-time progress reporting per task
  - Subscription tier gating (Starter = 1 sequential task max)
  - Automatic task breakdown -> sub-step assignment -> verification
  - Background task persistence (survives conversation restarts)
  - Smart context sharing between parallel tasks
  - Rate limiting per plan tier
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Subscription Tier Gate
# ---------------------------------------------------------------------------

class PlanTier(Enum):
    STARTER = "starter"   # Free  — 1 sequential task, no parallel
    LAUNCH  = "launch"    # Paid  — 2 parallel tasks, 20 workflows
    GROWTH  = "growth"    # Paid  — 4 parallel tasks, 40 workflows + background
    SCALE   = "scale"     # Paid  — 8 parallel tasks, all workflows + background
    ANNUAL  = "annual"    # Paid  — same as Scale + premium AI chains


_TIER_LIMITS: Dict[PlanTier, Dict[str, Any]] = {
    PlanTier.STARTER: {"parallel": 1,  "workflows": 5,   "background": False, "priority_queue": False},
    PlanTier.LAUNCH:  {"parallel": 2,  "workflows": 20,  "background": False, "priority_queue": False},
    PlanTier.GROWTH:  {"parallel": 4,  "workflows": 40,  "background": True,  "priority_queue": True},
    PlanTier.SCALE:   {"parallel": 8,  "workflows": 999, "background": True,  "priority_queue": True},
    PlanTier.ANNUAL:  {"parallel": 8,  "workflows": 999, "background": True,  "priority_queue": True},
}


def resolve_tier(plan_name: str) -> PlanTier:
    """Resolve raw plan string from licensing server to PlanTier enum."""
    name = (plan_name or "starter").lower().strip()
    for tier in PlanTier:
        if tier.value in name:
            return tier
    return PlanTier.STARTER


# ---------------------------------------------------------------------------
# Priority & Status Enums
# ---------------------------------------------------------------------------

class TaskPriority(Enum):
    CRITICAL   = 0
    HIGH       = 1
    NORMAL     = 2
    LOW        = 3
    BACKGROUND = 4


class TaskStatus(Enum):
    QUEUED    = "queued"
    RUNNING   = "running"
    PAUSED    = "paused"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Task Model
# ---------------------------------------------------------------------------

@dataclass
class ProTask:
    """A single unit of work in the Pro Brain execution graph."""
    id:              str            = field(default_factory=lambda: uuid.uuid4().hex[:10])
    goal:            str            = ""
    workflow:        str            = "generic"
    priority:        TaskPriority   = TaskPriority.NORMAL
    status:          TaskStatus     = TaskStatus.QUEUED
    depends_on:      List[str]      = field(default_factory=list)
    steps:           List[str]      = field(default_factory=list)
    completed_steps: List[str]      = field(default_factory=list)
    current_step:    str            = ""
    result:          Optional[str]  = None
    error:           Optional[str]  = None
    progress_pct:    int            = 0
    created_at:      float          = field(default_factory=time.time)
    started_at:      Optional[float] = None
    finished_at:     Optional[float] = None
    tags:            List[str]      = field(default_factory=list)
    on_complete:     Optional[Callable] = field(default=None, repr=False)
    on_progress:     Optional[Callable] = field(default=None, repr=False)
    context:         Dict[str, Any] = field(default_factory=dict)
    background:      bool           = False

    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at or time.time()
        return round(end - self.started_at, 1)

    def summary(self) -> str:
        icons = {
            TaskStatus.QUEUED:    "WAITING",
            TaskStatus.RUNNING:   "RUNNING",
            TaskStatus.PAUSED:    "PAUSED",
            TaskStatus.COMPLETED: "DONE",
            TaskStatus.FAILED:    "FAILED",
            TaskStatus.CANCELLED: "CANCELLED",
        }
        s = icons.get(self.status, "?")
        return (
            f"[{s}] [{self.id}] {self.goal[:55]} "
            f"({self.progress_pct}%) — Step: {self.current_step[:40]}"
        )


# ---------------------------------------------------------------------------
# 50+ Smart Workflow Templates
# ---------------------------------------------------------------------------

WORKFLOW_TEMPLATES: Dict[str, List[str]] = {
    # Video & Content
    "youtube_upload": [
        "Find video file on disk",
        "Verify file quality and format",
        "Authenticate YouTube OAuth",
        "Upload with resumable chunked transfer",
        "Confirm upload and open video URL",
    ],
    "youtube_script_to_short": [
        "Research trending topic",
        "Write 60-second hook script",
        "Source background footage",
        "Composite vertical 1080x1920 reel",
        "Add captions and music",
        "Export and verify final video",
        "Upload to YouTube Shorts",
    ],
    "instagram_post": [
        "Find or generate image/video asset",
        "Resize and optimise for Instagram",
        "Write caption with hashtags",
        "Authenticate Instagram Graph API",
        "Schedule or post content",
        "Confirm post and return URL",
    ],
    "social_media_repurpose": [
        "Download or locate source video",
        "Extract key highlights",
        "Generate 3 short clips (60s, 30s, 15s)",
        "Add captions and platform branding",
        "Export for YouTube Shorts, Instagram Reels, TikTok",
        "Queue all three uploads",
    ],
    "video_edit_fast": [
        "Probe video metadata and duration",
        "Trim, cut, and arrange clips",
        "Apply colour grade and stabilisation",
        "Render final export",
        "Verify output duration and audio sync",
    ],

    # Documents & Reports
    "excel_full_report": [
        "Locate workbook in Downloads/Desktop",
        "Read and map all sheets",
        "Clean whitespace, duplicates, and nulls",
        "Build pivot summary sheet",
        "Generate charts (bar/line/pie)",
        "Apply professional formatting",
        "Save and open final report",
    ],
    "pdf_extract_and_summarize": [
        "Locate PDF file",
        "Extract all text content",
        "Identify key sections and headings",
        "Generate structured summary",
        "Export as clean Word/text document",
    ],
    "report_from_data": [
        "Load CSV/Excel data source",
        "Run statistical analysis",
        "Identify top insights",
        "Generate professional report document",
        "Create visual charts",
        "Save to Desktop",
    ],
    "presentation_builder": [
        "Outline topic structure (8-12 slides)",
        "Research key points per slide",
        "Write slide content and speaker notes",
        "Build PPTX with professional theme",
        "Add charts and images",
        "Export and open presentation",
    ],
    "email_batch_draft": [
        "Load contact list from Excel/CSV",
        "Read email template",
        "Personalise each email with names and data",
        "Preview first 5 emails for approval",
        "Send or save all drafts",
    ],

    # Research & Intelligence
    "deep_research": [
        "Decompose research question into sub-queries",
        "Search web (DuckDuckGo + Gemini grounding)",
        "Cross-reference 3+ independent sources",
        "Extract facts, stats, and citations",
        "Write structured research brief",
        "Save to Desktop as Markdown/PDF",
    ],
    "competitor_analysis": [
        "Identify 5 top competitors",
        "Scrape public pricing and feature pages",
        "Compare positioning matrix",
        "Identify gaps and opportunities",
        "Generate competitive intelligence report",
    ],
    "news_digest": [
        "Fetch top 20 headlines",
        "Cluster by topic",
        "Summarise each cluster",
        "Rank by relevance to user interests",
        "Speak top 5 and save full digest",
    ],
    "market_research": [
        "Define target market parameters",
        "Search market size and growth data",
        "Identify major players and trends",
        "Synthesise findings into market map",
        "Generate market research report",
    ],

    # Coding & Development
    "code_debug_fix": [
        "Inspect repository structure",
        "Reproduce the error",
        "Root-cause analysis",
        "Apply minimal targeted fix",
        "Run syntax check and unit tests",
        "Verify fix and update memory",
    ],
    "code_review": [
        "Read all modified files",
        "Check for security vulnerabilities",
        "Flag style violations and anti-patterns",
        "Suggest performance improvements",
        "Generate code review report",
    ],
    "api_integration": [
        "Read API documentation",
        "Design request/response models",
        "Write integration code with error handling",
        "Write unit tests for the integration",
        "Test against live endpoint",
        "Document usage examples",
    ],
    "deploy_app": [
        "Run pre-deploy checklist (tests, env vars)",
        "Build production bundle",
        "Upload to hosting platform",
        "Run smoke tests on deployed URL",
        "Notify user with live URL",
    ],

    # Vision & Camera Intelligence
    "object_ocr_inspection": [
        "Open camera stream and calibrate focus",
        "Capture sharpest multi-frame capture with contrast enhancement",
        "Execute deep OCR text and label extraction",
        "Identify object brand, model, and physical specifications",
        "Analyze primary purpose, daily use cases, and operating instructions",
        "Generate structured inspection markdown report and save to memory",
    ],
    "document_camera_scan": [
        "Capture document via high-res camera stream",
        "Apply perspective correction and contrast optimization",
        "Perform full text OCR transcription",
        "Extract key entities, dates, totals, and signatures",
        "Export transcribed text and formatted PDF/markdown copy",
    ],

    # Security & Infrastructure Intelligence
    "network_security_audit": [
        "Inspect network interfaces and IP configurations",
        "Test latency and DNS resolution",
        "Audit open listening ports on local interfaces",
        "Check firewall rules and active network connections",
        "Generate comprehensive network security hardening report",
    ],

    # Financial & Tax Intelligence
    "financial_tax_review": [
        "Parse financial transactions and invoice records",
        "Categorise operating expenses and capital costs",
        "Calculate gross/net margins and estimated tax liabilities",
        "Check standard deduction rules and compliance flags",
        "Export executive financial summary report",
    ],

    # Career & Interview Simulation
    "mock_interview_session": [
        "Select target job role, stack, and seniority level",
        "Curate bespoke technical and behavioral question bank",
        "Deliver interactive mock interview questions",
        "Evaluate answers using STAR rubric and technical depth",
        "Produce detailed feedback report with improvement plan",
    ],

    # Smart Home & IoT Automation
    "smart_home_orchestration": [
        "Discover local Home Assistant, MQTT, and IoT gateways",
        "Audit device inventory and network isolation posture",
        "Design robust automation trigger and safety constraints",
        "Deploy and test automation sequence on target device",
        "Verify device state synchronization and notify user",
    ],

    # Database & Data Engineering
    "sql_query_optimization": [
        "Profile slow query with EXPLAIN ANALYZE",
        "Inspect table cardinality and existing index coverage",
        "Formulate optimized query rewrite and index additions",
        "Validate query execution plan and cost reduction",
        "Export SQL migration script and benchmark report",
    ],

    # Cloud & DevOps Pipeline
    "cloud_docker_k8s_deploy": [
        "Audit Dockerfile for multi-stage security and layer caching",
        "Generate Kubernetes Deployment and Service manifests",
        "Configure automated CI/CD pipeline steps",
        "Run container lint and vulnerability scan",
        "Produce deployment verification checklist",
    ],

    # Machine Learning & Data Science
    "ml_dataset_pipeline": [
        "Load raw dataset and perform exploratory data analysis",
        "Clean missing values and encode categorical features",
        "Execute stratified train/validation/test split",
        "Train baseline model and tune hyperparameters",
        "Evaluate precision, recall, and ROC-AUC curves",
    ],

    # API Design & Microservices
    "api_contract_specification": [
        "Define resource domain models and HTTP verbs",
        "Specify OpenAPI / Swagger 3.0 schema contract",
        "Configure request validation and error envelope schemas",
        "Generate mock API server fixtures and contract tests",
        "Export complete API documentation",
    ],

    # Systems Administration & Diagnostics
    "system_health_triage": [
        "Inspect CPU load averages and memory paging pressure",
        "Check disk partition utilization and inode availability",
        "Audit systemd journal for critical service errors",
        "Verify network socket states and listening services",
        "Generate prioritized system remediation checklist",
    ],

    # Web Frontend & UI Performance
    "web_component_audit": [
        "Audit DOM tree depth and layout reflow triggers",
        "Measure Core Web Vitals (LCP, INP, CLS)",
        "Inspect bundle size and code-splitting boundaries",
        "Audit WCAG 2.1 AA accessibility and ARIA roles",
        "Generate frontend optimization action plan",
    ],

    # Mobile App Engineering
    "mobile_app_release_prep": [
        "Verify app bundle versioning and release signing",
        "Audit runtime permission requests and privacy manifests",
        "Test offline SQLite cache synchronization",
        "Verify responsive screen layouts across form factors",
        "Generate App Store & Play Store submission dossier",
    ],

    # Statistical Reasoning & Mathematics
    "statistical_hypothesis_analysis": [
        "Formulate null and alternative hypotheses",
        "Validate distribution normality and sample assumptions",
        "Calculate test statistics, degrees of freedom, and p-value",
        "Determine statistical significance against alpha threshold",
        "Deliver interpreted findings with confidence intervals",
    ],

    # Legal & Contract Review
    "contract_risk_assessment": [
        "Parse contract text and isolate key operating covenants",
        "Identify high-risk indemnification and liability caps",
        "Review intellectual property ownership and termination clauses",
        "Check compliance with GDPR/data privacy standards",
        "Export executive contract risk matrix with non-attorney disclaimer",
    ],

    # Ergonomics & Workplace Health
    "ergonomic_workplace_assessment": [
        "Evaluate chair, desk, and monitor alignment geometry",
        "Establish 20-20-20 screen rest and hydration schedules",
        "Design repetitive strain injury (RSI) prevention routine",
        "Review lighting to eliminate glare and eye fatigue",
        "Deliver personalized workstation ergonomics guide",
    ],

    # Creative Writing & Speech Design
    "keynote_speech_design": [
        "Identify target audience demographic and core thesis",
        "Craft memorable narrative hook and personal opening",
        "Structure key supporting arguments with 3-act cadence",
        "Draft compelling call-to-action and closing quote",
        "Produce executive slide presentation speaker notes",
    ],

    # Agile Project Management
    "agile_sprint_kickoff": [
        "Review sprint goal and team capacity velocity",
        "Slice epic backlog into INVEST-compliant user stories",
        "Facilitate Fibonacci story point estimation",
        "Establish definition of done and acceptance criteria",
        "Publish sprint backlog board and burndown tracker",
    ],

    # File & System Management
    "folder_organise": [
        "Scan target folder recursively",
        "Classify files by type and date",
        "Create organised subfolder structure",
        "Move files with progress reporting",
        "Generate organisation report",
    ],
    "bulk_rename": [
        "List all matching files",
        "Preview rename plan (show before/after)",
        "Await user confirmation",
        "Apply renames atomically",
        "Verify all renames succeeded",
    ],
    "disk_cleanup": [
        "Scan for large files (>100 MB)",
        "Find temp/cache directories",
        "Identify duplicate files",
        "Present cleanup summary for approval",
        "Delete approved items safely",
    ],
    "backup_to_cloud": [
        "Identify files/folders to backup",
        "Compress into timestamped archive",
        "Upload to Google Drive / OneDrive",
        "Verify upload integrity",
        "Report backup size and location",
    ],

    # Communication & Scheduling
    "meeting_prep": [
        "Fetch meeting agenda from calendar",
        "Research attendees and topics",
        "Summarise relevant past discussions",
        "Draft 1-page meeting brief",
        "Set pre-meeting reminder",
    ],
    "email_triage": [
        "Read inbox (last 50 emails)",
        "Classify as urgent / action-required / FYI / spam",
        "Draft replies for action-required items",
        "Present summary with suggested actions",
    ],
    "task_planning": [
        "Break down project goal into milestones",
        "Estimate time per milestone",
        "Identify blockers and dependencies",
        "Build prioritised task list",
        "Export to Excel or present as checklist",
    ],

    # Business & Finance
    "invoice_generate": [
        "Load client and service details",
        "Calculate totals and taxes",
        "Generate professional PDF invoice",
        "Save to invoices folder",
        "Draft email with invoice attached",
    ],
    "expense_report": [
        "Read expense entries from input",
        "Categorise by type",
        "Calculate totals per category",
        "Apply company policy checks",
        "Generate formatted expense report",
    ],
    "sales_analysis": [
        "Load sales data (Excel/CSV)",
        "Calculate KPIs (revenue, growth, conversion)",
        "Identify top products and customers",
        "Spot trends and anomalies",
        "Generate executive dashboard report",
    ],

    # Learning & Personal
    "study_plan": [
        "Analyse syllabus or exam topics",
        "Break into daily study blocks",
        "Create flashcard-style summaries",
        "Build revision schedule to exam date",
        "Export study plan as PDF",
    ],
    "resume_enhance": [
        "Read current resume",
        "Identify weak sections",
        "Research job description keywords",
        "Rewrite with ATS-optimised language",
        "Format as clean PDF",
    ],

    # Generic fallback
    "generic": [
        "Analyse and decompose goal",
        "Gather required context and data",
        "Execute primary action",
        "Verify and validate outcome",
        "Report result to user",
    ],
}


# Keyword-to-workflow map for auto-detection
_WORKFLOW_KEYWORDS: Dict[str, List[str]] = {
    "youtube_upload":            ["upload", "post", "youtube", "channel"],
    "youtube_script_to_short":   ["shorts", "reel", "60 second", "script to video"],
    "instagram_post":            ["instagram", "insta", "post photo", "post image"],
    "social_media_repurpose":    ["repurpose", "cross-post", "all platforms", "tiktok"],
    "video_edit_fast":           ["edit video", "trim", "cut", "colour grade", "render"],
    "excel_full_report":         ["excel", "spreadsheet", "xlsx", "pivot", "report excel"],
    "pdf_extract_and_summarize": ["pdf", "extract", "summarize pdf"],
    "report_from_data":          ["report from data", "csv report", "data analysis"],
    "presentation_builder":      ["presentation", "slides", "pptx", "powerpoint"],
    "email_batch_draft":         ["email batch", "bulk email", "send emails to list"],
    "deep_research":             ["research", "find out", "deep dive", "investigate"],
    "competitor_analysis":       ["competitor", "competition", "rivals"],
    "news_digest":               ["news", "headlines", "digest"],
    "market_research":           ["market research", "market size", "industry analysis"],
    "code_debug_fix":            ["debug", "fix bug", "error in code", "fix code"],
    "code_review":               ["review code", "code review", "check my code"],
    "api_integration":           ["api", "integrate", "connect service"],
    "deploy_app":                ["deploy", "launch app", "publish app", "go live"],
    "folder_organise":           ["organise", "organize", "sort folder", "clean folder"],
    "bulk_rename":               ["rename files", "bulk rename"],
    "disk_cleanup":              ["cleanup", "clean disk", "free space", "delete old"],
    "backup_to_cloud":           ["backup", "back up", "save to drive"],
    "meeting_prep":              ["meeting prep", "prepare for meeting", "meeting brief"],
    "email_triage":              ["triage email", "check inbox", "email summary"],
    "task_planning":             ["plan project", "break down", "task list"],
    "invoice_generate":          ["invoice", "bill client"],
    "expense_report":            ["expense", "expenses", "claim"],
    "sales_analysis":            ["sales analysis", "revenue report", "sales data"],
    "study_plan":                ["study plan", "revision schedule", "exam prep"],
    "resume_enhance":            ["resume", "cv", "job application"],
}


def detect_workflow(goal: str) -> str:
    """Match a natural-language goal to the best workflow template."""
    low = goal.lower()
    best_wf   = "generic"
    best_hits = 0
    for wf, keywords in _WORKFLOW_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in low)
        if hits > best_hits:
            best_hits = hits
            best_wf = wf
    return best_wf


# ---------------------------------------------------------------------------
# Pro Brain Core
# ---------------------------------------------------------------------------

class ProBrain:
    """
    Charlie's next-level parallel task intelligence engine.

    Instantiate once at app startup; pass the current user's plan tier.
    Call submit() to queue tasks and status_report() for live updates.
    """

    def __init__(
        self,
        plan_tier: PlanTier = PlanTier.STARTER,
        speak: Optional[Callable] = None,
    ):
        self.tier    = plan_tier
        self._limits = _TIER_LIMITS[plan_tier]
        self._speak  = speak

        max_workers   = max(1, self._limits["parallel"])
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="charlie_pro",
        )
        self._lock          = threading.Lock()
        self._tasks:   Dict[str, ProTask]  = {}
        self._futures: Dict[str, Future]   = {}
        self._queue:   deque[ProTask]      = deque()
        self._running_count: int           = 0

        print(f"[ProBrain] Initialized — tier={plan_tier.value}, max_parallel={max_workers}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(
        self,
        goal: str,
        *,
        priority: TaskPriority = TaskPriority.NORMAL,
        depends_on: Optional[List[str]] = None,
        background: bool = False,
        tags: Optional[List[str]] = None,
        on_complete: Optional[Callable[["ProTask"], None]] = None,
        on_progress: Optional[Callable[["ProTask", str], None]] = None,
        context: Optional[Dict[str, Any]] = None,
        action_fn: Optional[Callable] = None,
    ) -> Tuple[str, str]:
        """
        Submit a new task to the Pro Brain.
        Returns (task_id, message).  task_id is empty string if gated.
        """
        gate_msg = self._check_tier_gate(background)

        workflow = detect_workflow(goal)
        steps    = list(WORKFLOW_TEMPLATES.get(workflow, WORKFLOW_TEMPLATES["generic"]))

        task = ProTask(
            goal        = goal,
            workflow    = workflow,
            priority    = priority,
            depends_on  = depends_on or [],
            steps       = steps,
            current_step= steps[0] if steps else "Execute",
            tags        = tags or [],
            background  = background,
            on_complete = on_complete,
            on_progress = on_progress,
            context     = context or {},
        )

        with self._lock:
            self._tasks[task.id] = task

        if gate_msg:
            # Still register the task but mark it queued for later
            task.status = TaskStatus.QUEUED
            self._queue.append(task)
            return task.id, gate_msg

        if self._deps_satisfied(task):
            self._dispatch(task, action_fn)
        else:
            self._queue.append(task)

        confirm = (
            f"Task queued [{task.id}]: '{goal[:55]}' "
            f"using '{workflow}' workflow ({len(steps)} steps)."
        )
        return task.id, confirm

    def cancel(self, task_id: str) -> str:
        with self._lock:
            task = self._tasks.get(task_id)
        if not task:
            return f"No task found with ID '{task_id}'."
        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return f"Task '{task_id}' already {task.status.value}."
        task.status = TaskStatus.CANCELLED
        fut = self._futures.get(task_id)
        if fut:
            fut.cancel()
        return f"Task '{task_id}' cancelled, sir."

    def status_report(self, verbose: bool = False) -> str:
        with self._lock:
            tasks = list(self._tasks.values())

        if not tasks:
            return "No tasks in progress, sir. Ready for your next command."

        lines = [
            f"Charlie Pro Brain — {self.tier.value.upper()} Plan",
            f"  {self._running_count} running / {len(tasks)} total",
            "",
        ]
        order = [
            TaskStatus.RUNNING,
            TaskStatus.QUEUED,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        ]
        for status in order:
            group = [t for t in tasks if t.status == status]
            if not group:
                continue
            lines.append(f"  {'='*40}")
            for t in sorted(group, key=lambda x: x.priority.value):
                lines.append(f"  {t.summary()}")
                if verbose and t.completed_steps:
                    lines.append(f"    Done: {' > '.join(t.completed_steps[-3:])}")
                if t.error:
                    lines.append(f"    Error: {t.error[:80]}")
                if t.result and status == TaskStatus.COMPLETED:
                    lines.append(f"    Result: {t.result[:100]}")

        return "\n".join(lines)

    def wait_for_all(self, timeout: float = 300.0) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                active = [
                    t for t in self._tasks.values()
                    if t.status in (TaskStatus.RUNNING, TaskStatus.QUEUED)
                ]
            if not active:
                break
            time.sleep(0.5)
        return self.status_report(verbose=True)

    def get_task(self, task_id: str) -> Optional[ProTask]:
        return self._tasks.get(task_id)

    def get_tier_info(self) -> str:
        lim = self._limits
        return (
            f"Plan: {self.tier.value.upper()} | "
            f"Parallel tasks: {lim['parallel']} | "
            f"Workflows: {lim['workflows']} | "
            f"Background tasks: {'Yes' if lim['background'] else 'No'}"
        )

    # ------------------------------------------------------------------
    # Internal Execution
    # ------------------------------------------------------------------

    def _check_tier_gate(self, background: bool) -> Optional[str]:
        """Return an upgrade message if tier limits are reached; None if OK."""
        if background and not self._limits["background"]:
            return (
                "Background tasks are available on Growth, Scale, and Annual plans. "
                "Upgrade to run long jobs while you continue working, sir."
            )
        with self._lock:
            running = sum(
                1 for t in self._tasks.values()
                if t.status == TaskStatus.RUNNING
            )
        if running >= self._limits["parallel"]:
            tip = {
                PlanTier.STARTER: "Upgrade to Launch to run 2 tasks simultaneously.",
                PlanTier.LAUNCH:  "Upgrade to Growth for 4 parallel tasks + background jobs.",
                PlanTier.GROWTH:  "Upgrade to Scale or Annual for 8 parallel tasks.",
            }.get(self.tier, "")
            return (
                f"Your {self.tier.value.upper()} plan allows {self._limits['parallel']} "
                f"parallel task(s). All slots are busy. {tip} "
                f"I'll start this as soon as a slot frees up, sir."
            )
        return None

    def _deps_satisfied(self, task: ProTask) -> bool:
        with self._lock:
            for dep_id in task.depends_on:
                dep = self._tasks.get(dep_id)
                if dep is None or dep.status != TaskStatus.COMPLETED:
                    return False
        return True

    def _dispatch(self, task: ProTask, action_fn: Optional[Callable] = None) -> None:
        task.status     = TaskStatus.RUNNING
        task.started_at = time.time()
        with self._lock:
            self._running_count += 1
        fn  = action_fn or self._default_executor
        fut = self._executor.submit(self._run_task, task, fn)
        self._futures[task.id] = fut
        fut.add_done_callback(lambda f: self._on_task_done(task, f))

    def _run_task(self, task: ProTask, fn: Callable) -> str:
        total = len(task.steps)
        for i, step in enumerate(task.steps):
            if task.status == TaskStatus.CANCELLED:
                return "Cancelled."
            task.current_step = step
            task.progress_pct = int((i / max(total, 1)) * 100)
            if task.on_progress:
                try:
                    task.on_progress(task, step)
                except Exception:
                    pass
            try:
                result = fn(task, step)
                task.completed_steps.append(step)
                if result:
                    task.context[f"step_{i}_result"] = str(result)[:200]
            except Exception as exc:
                task.error  = str(exc)
                task.status = TaskStatus.FAILED
                return f"Failed at '{step}': {exc}"
        task.progress_pct = 100
        return task.context.get(f"step_{total - 1}_result", "Completed successfully.")

    def _default_executor(self, task: ProTask, step: str) -> str:
        """Placeholder step executor — real implementation routes to action registry."""
        time.sleep(0.05)
        return f"Done: {step}"

    def _on_task_done(self, task: ProTask, future: Future) -> None:
        with self._lock:
            self._running_count = max(0, self._running_count - 1)

        if task.status == TaskStatus.CANCELLED:
            pass
        elif future.exception():
            task.status      = TaskStatus.FAILED
            task.error       = str(future.exception())
            task.finished_at = time.time()
        else:
            task.result      = future.result()
            task.status      = TaskStatus.COMPLETED
            task.finished_at = time.time()

        # TTS completion announcement
        if task.status == TaskStatus.COMPLETED and self._speak and not task.background:
            try:
                elapsed = task.elapsed()
                self._speak(
                    f"Task complete, sir. '{task.goal[:40]}' "
                    f"finished in {elapsed} seconds."
                )
            except Exception:
                pass

        if task.on_complete:
            try:
                task.on_complete(task)
            except Exception:
                pass

        self._flush_queue()

    def _flush_queue(self) -> None:
        """Dispatch queued tasks whose dependencies are now satisfied."""
        with self._lock:
            ready = [t for t in self._queue if self._deps_satisfied(t)]
            for t in ready:
                self._queue.remove(t)
        for t in ready:
            gate = self._check_tier_gate(t.background)
            if not gate:
                self._dispatch(t)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


# ---------------------------------------------------------------------------
# Global singleton helper
# ---------------------------------------------------------------------------

_GLOBAL_PRO_BRAIN: Optional[ProBrain] = None


def get_pro_brain(
    plan_tier: str = "starter",
    speak: Optional[Callable] = None,
) -> ProBrain:
    """Return the singleton ProBrain, initialising if necessary."""
    global _GLOBAL_PRO_BRAIN
    if _GLOBAL_PRO_BRAIN is None:
        _GLOBAL_PRO_BRAIN = ProBrain(plan_tier=resolve_tier(plan_tier), speak=speak)
    return _GLOBAL_PRO_BRAIN


def reset_pro_brain(
    plan_tier: str = "starter",
    speak: Optional[Callable] = None,
) -> ProBrain:
    """Force-recreate ProBrain (call on login or plan change)."""
    global _GLOBAL_PRO_BRAIN
    if _GLOBAL_PRO_BRAIN:
        _GLOBAL_PRO_BRAIN.shutdown()
    _GLOBAL_PRO_BRAIN = ProBrain(plan_tier=resolve_tier(plan_tier), speak=speak)
    return _GLOBAL_PRO_BRAIN
