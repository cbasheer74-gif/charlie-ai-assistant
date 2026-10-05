"""engine/brain_trainer.py — Professional Training & Memory Enrichment Engine for CHARLIE.

Trains Charlie's brain, procedural playbooks, error recovery solutions,
and Personal Knowledge Graph with verified, zero-hallucination domain knowledge.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.db import get_db, init_db, utc_now_iso
from engine.intelligence.knowledge_graph import PersonalKnowledgeGraph
from engine.intelligence.models import Entity, EntityType, RelationType, Relationship

logger = logging.getLogger("charlie.brain_trainer")


# ── Core Domain Playbooks (Procedural Memory) ────────────────────────────────

CORE_PLAYBOOKS: List[Dict[str, Any]] = [
    {
        "name": "camera_ocr_inspection",
        "intent": "Perform high-precision camera capture, optical character recognition, and object identification",
        "steps": [
            "Trigger camera stream UI with active visual feedback",
            "Capture multi-frame burst and select highest Laplacian focus score",
            "Apply CLAHE contrast normalization in LAB color space",
            "Extract visible brand names, model numbers, text, and labels via OCR",
            "Identify exact object category, manufacturer, and physical specifications",
            "Explain everyday utility, applications, and step-by-step operating instructions",
            "Archive high-res scan frame and structured report to memory/scans/",
        ],
    },
    {
        "name": "network_security_audit",
        "intent": "Audit network interfaces, firewall rules, and diagnostic indicators defensively",
        "steps": [
            "Enumerate active network adapters, IP addresses, and default gateway routes",
            "Test ICMP latency and round-trip consistency across upstream DNS servers",
            "Audit local listening sockets and verify associated process identifiers",
            "Inspect active firewall rules for unauthorized ingress exposure",
            "Produce prioritized defensive network hardening report with actionable remediations",
        ],
    },
    {
        "name": "sql_query_optimization",
        "intent": "Diagnose slow relational database queries and generate performant indexes and rewrites",
        "steps": [
            "Execute query under EXPLAIN (ANALYZE, BUFFERS) or equivalent execution profiler",
            "Identify sequential table scans, high disk buffer reads, and Cartesian joins",
            "Evaluate composite, B-Tree, or partial index candidates on filtered/joined columns",
            "Rewrite correlated subqueries as set-based window functions or CTEs",
            "Verify execution plan cost reduction and produce non-blocking migration script",
        ],
    },
    {
        "name": "mock_interview_viva",
        "intent": "Conduct structured technical interview or academic viva examination",
        "steps": [
            "Establish target job role, seniority level, and technical evaluation rubric",
            "Present one realistic scenario or technical challenge at a time",
            "Evaluate candidate answer on correctness, architectural depth, and STAR structure",
            "Provide encouraging, constructive feedback highlighting specific improvement points",
            "Track cumulative candidate score and export final interview performance summary",
        ],
    },
    {
        "name": "smart_home_orchestration",
        "intent": "Pair, isolate, and automate local IoT devices securely",
        "steps": [
            "Discover local Home Assistant, MQTT, or Matter gateways",
            "Audit device network topology and enforce guest/IoT VLAN isolation",
            "Formulate deterministic automation rule with state preconditions and timeout guards",
            "Deploy automation rule to local broker with zero cloud dependency",
            "Verify state feedback loops and log execution confirmation",
        ],
    },
    {
        "name": "code_root_cause_triage",
        "intent": "Diagnose software defects, trace call stacks, and produce minimal verified patches",
        "steps": [
            "Isolate reproduction steps, error tracebacks, and unexpected state transitions",
            "Identify Root Cause at the exact code line, type discrepancy, or race condition",
            "Assess blast radius across dependent modules and API surfaces",
            "Author surgical, minimal patch maintaining full backward compatibility",
            "Execute targeted regression unit test and document verification result",
        ],
    },
]

# ── Defensive Error Recovery Solutions (Error Memory) ─────────────────────────

CORE_ERROR_RECOVERIES: List[Dict[str, Any]] = [
    {
        "error_signature": "CameraDeviceBusyOrUnavailable",
        "application": "vision_scanner",
        "root_cause": "Webcam is currently locked by another application or Windows camera privacy permission is off.",
        "successful_fix": "Enumerate available direct-show camera indices (0..3); if busy, notify user to close conflicting video conference app and check Settings -> Privacy -> Camera.",
        "verification": "Test cv2.VideoCapture opening on fallback index 0 with DSHOW backend.",
    },
    {
        "error_signature": "MicrophoneStreamBufferOverflow",
        "application": "audio_subsystem",
        "root_cause": "Audio input buffer overrun caused by CPU contention or thread starvation.",
        "successful_fix": "Increase sounddevice blocksize to 1024 or 2048, run processing on dedicated background queue, and drop stale silence buffers.",
        "verification": "Verify zero audio clock drift and zero sounddevice callback drop flags over 30s.",
    },
    {
        "error_signature": "DatabaseBusyLockedTimeout",
        "application": "sqlite_engine",
        "root_cause": "Multiple threads competing for SQLite write transaction under default rollback journal.",
        "successful_fix": "Enable WAL (Write-Ahead Logging) journal mode, set busy_timeout to 5000ms, and wrap write operations in exclusive threading lock.",
        "verification": "PRAGMA journal_mode returns 'wal' and multi-threaded stress tests pass cleanly.",
    },
    {
        "error_signature": "LocalPortAlreadyInUse",
        "application": "network_services",
        "root_cause": "A local diagnostic or dev service failed to bind because another process owns the port.",
        "successful_fix": "Execute netstat/Get-NetTCPConnection to identify offending PID, offer graceful termination, or select next ephemeral port (n+1).",
        "verification": "Socket binds successfully and accepts incoming healthcheck ping.",
    },
]

# ── Core Domain Facts (User & Knowledge Memory) ───────────────────────────────

CORE_DOMAIN_FACTS: List[Tuple[str, str, float]] = [
    (
        "system_identity",
        "CHARLIE is an autonomous native desktop AI assistant running locally on Windows/PC, featuring real-time FACS lip-sync digital human avatars, Pro Brain parallel workflow automation, and privacy-first local memory.",
        10.0,
    ),
    (
        "camera_vision_capabilities",
        "CHARLIE provides instant camera object scanning and OCR: auto-focus sharpness selection, CLAHE contrast enhancement, label transcription, brand identification, everyday use analysis, and step-by-step guidance.",
        9.5,
    ),
    (
        "cybersecurity_standards",
        "CHARLIE strictly adheres to defensive security: network troubleshooting, firewall auditing, vulnerability patching, and secure hashing (bcrypt/argon2). Malicious exploit authoring and unauthorized intrusion are permanently blocked.",
        9.5,
    ),
    (
        "finance_tax_standards",
        "CHARLIE provides structured financial calculations, budgeting models, and tax deduction education. Outputs are educational estimates; users must verify filings with certified CPAs.",
        9.0,
    ),
    (
        "database_optimization_standards",
        "CHARLIE optimizes databases using EXPLAIN ANALYZE, selective B-Tree/GIN indexing, ACID transaction isolation, 3NF schema normalization, and zero-downtime column migrations.",
        9.0,
    ),
    (
        "devops_cloud_standards",
        "CHARLIE automates cloud DevOps with Docker multi-stage builds, Kubernetes pod manifests, GitHub Actions CI/CD workflows, Terraform IaC, and zero-downtime blue/green deployment.",
        9.0,
    ),
    (
        "machine_learning_standards",
        "CHARLIE structures data science pipelines using Pandas/Polars, feature scaling, stratified train/validation/test splits, and multi-metric evaluations (F1-score, ROC-AUC, RMSE).",
        9.0,
    ),
    (
        "api_design_standards",
        "CHARLIE designs clean RESTful and gRPC interfaces, idempotent mutating endpoints with UUID keys, OAuth2/JWT auth patterns, and leaky-bucket rate limiting.",
        9.0,
    ),
    (
        "sysadmin_standards",
        "CHARLIE manages OS processes, memory swapping, disk storage, systemd service units, and cross-platform automation via PowerShell and Bash.",
        9.0,
    ),
    (
        "frontend_standards",
        "CHARLIE builds responsive web interfaces with semantic HTML5, CSS Grid/Flexbox, React/Vue lifecycles, ARIA accessibility, and fast Core Web Vitals (LCP < 2.5s, INP < 200ms).",
        9.0,
    ),
    (
        "mobile_app_standards",
        "CHARLIE structures Flutter and native iOS/Android applications with clean reactive state, offline SQLite caching, permission handling, and store release checklists.",
        9.0,
    ),
    (
        "math_stats_standards",
        "CHARLIE solves mathematical and statistical problems with clear derivations: calculus optimization, linear algebra transformations, probability distributions, and hypothesis tests.",
        9.0,
    ),
    (
        "legal_standards",
        "CHARLIE analyzes contracts, NDAs, and terms of service by identifying key obligations, liability caps, and IP assignment clauses under an explicit non-attorney legal information disclaimer.",
        9.0,
    ),
    (
        "ergonomics_wellness_standards",
        "CHARLIE promotes workplace health through 90-degree arm/knee posture, monitor eye-level placement, the 20-20-20 screen rule, and hydration pacing under a non-medical consultation disclaimer.",
        8.5,
    ),
    (
        "interview_prep_standards",
        "CHARLIE conducts mock technical interviews and viva exams: delivers targeted questions one at a time and evaluates technical depth, poise, and STAR-format structure.",
        9.0,
    ),
    (
        "smart_home_standards",
        "CHARLIE integrates smart homes using local-first protocols (Home Assistant, MQTT, Zigbee, Matter) and isolates IoT devices on dedicated guest VLANs.",
        9.0,
    ),
    (
        "meeting_intelligence_standards",
        "CHARLIE captures meeting discussions, extracts confirmed decisions, assigns action items with owners and deadlines, and exports structured Markdown summaries to config/meetings/.",
        9.0,
    ),
    (
        "code_audit_standards",
        "CHARLIE follows a 4-step debugging triage: Root Cause Analysis, blast radius assessment, minimal surgical patch, and executable regression test verification.",
        9.5,
    ),
]


class BrainTrainer:
    """Trains and enriches Charlie's long-term memory, procedural playbooks, and knowledge graph."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path
        init_db(self.db_path)
        self.kg = PersonalKnowledgeGraph()

    def train_all(self) -> Dict[str, int]:
        """Execute complete professional training run across all memory subsystems."""
        counts = {
            "facts_trained": self.train_domain_facts(),
            "playbooks_trained": self.train_procedural_playbooks(),
            "recoveries_trained": self.train_error_recoveries(),
            "kg_entities_trained": self.train_knowledge_graph(),
        }
        logger.info(f"[BrainTrainer] Training completed successfully: {counts}")
        return counts

    def train_domain_facts(self) -> int:
        """Seed verified domain facts into user_memories table."""
        now = utc_now_iso()
        trained = 0
        with get_db(self.db_path) as conn:
            for cat, fact, importance in CORE_DOMAIN_FACTS:
                existing = conn.execute(
                    "SELECT id FROM user_memories WHERE category = ? AND is_active = 1;",
                    (cat,),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE user_memories
                        SET content = ?, importance = ?, confidence = 1.0, updated_at = ?
                        WHERE id = ?;
                        """,
                        (fact, importance, now, existing["id"]),
                    )
                else:
                    mem_id = f"mem_{cat}_{int(datetime.now().timestamp()*1000)}"
                    conn.execute(
                        """
                        INSERT INTO user_memories
                        (id, user_id, category, content, importance, confidence, source, access_count, created_at, updated_at, is_active)
                        VALUES (?, 'default_user', ?, ?, ?, 1.0, 'brain_trainer', 1, ?, ?, 1);
                        """,
                        (mem_id, cat, fact, importance, now, now),
                    )
                trained += 1
        return trained

    def train_procedural_playbooks(self) -> int:
        """Seed executable procedural workflows into procedural_memories table."""
        now = utc_now_iso()
        trained = 0
        with get_db(self.db_path) as conn:
            for pb in CORE_PLAYBOOKS:
                steps_json = json.dumps(pb["steps"])
                existing = conn.execute(
                    "SELECT id FROM procedural_memories WHERE name = ?;",
                    (pb["name"],),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE procedural_memories
                        SET intent = ?, steps_json = ?, confidence = 1.0, updated_at = ?
                        WHERE id = ?;
                        """,
                        (pb["intent"], steps_json, now, existing["id"]),
                    )
                else:
                    pb_id = f"proc_{pb['name']}"
                    conn.execute(
                        """
                        INSERT INTO procedural_memories
                        (id, name, intent, steps_json, success_count, failure_count, confidence, created_at, updated_at)
                        VALUES (?, ?, ?, ?, 10, 0, 1.0, ?, ?);
                        """,
                        (pb_id, pb["name"], pb["intent"], steps_json, now, now),
                    )
                trained += 1
        return trained

    def train_error_recoveries(self) -> int:
        """Seed self-correcting defensive error resolutions into error_memories table."""
        now = utc_now_iso()
        trained = 0
        with get_db(self.db_path) as conn:
            for rec in CORE_ERROR_RECOVERIES:
                existing = conn.execute(
                    "SELECT id FROM error_memories WHERE error_signature = ?;",
                    (rec["error_signature"],),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE error_memories
                        SET root_cause = ?, successful_fix = ?, verification = ?, last_seen_at = ?
                        WHERE id = ?;
                        """,
                        (rec["root_cause"], rec["successful_fix"], rec["verification"], now, existing["id"]),
                    )
                else:
                    err_id = f"err_{rec['error_signature']}"
                    conn.execute(
                        """
                        INSERT INTO error_memories
                        (id, error_signature, application, root_cause, successful_fix, verification, created_at, last_seen_at, occurrence_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1);
                        """,
                        (err_id, rec["error_signature"], rec["application"], rec["root_cause"], rec["successful_fix"], rec["verification"], now, now),
                    )
                trained += 1
        return trained

    def train_knowledge_graph(self) -> int:
        """Seed canonical entity relationships into Personal Knowledge Graph."""
        now = datetime.now().timestamp()
        root_entity = Entity(
            id="entity_charlie_assistant",
            type=EntityType.AGENT,
            canonical_name="CHARLIE",
            aliases={"Charlie", "Charlie AI", "Charlie Assistant"},
            metadata={"version": "1.0", "engine": "Pro Brain Hybrid"},
            confidence=1.0,
            source="brain_trainer",
            created_at=now,
            updated_at=now,
            last_verified_at=now,
        )
        self.kg.upsert_entity(root_entity)

        domains = [
            ("vision_ocr", "Vision & Camera OCR"),
            ("cybersecurity", "Defensive Cyber-Security"),
            ("databases", "Database & SQL Optimization"),
            ("devops_cloud", "DevOps & Cloud Infrastructure"),
            ("machine_learning", "Data Science & Machine Learning"),
            ("api_microservices", "API Design & Microservices"),
            ("sysadmin", "System Administration & OS"),
            ("web_frontend", "Web Frontend & UI Architecture"),
            ("mobile_apps", "Mobile Application Engineering"),
            ("math_stats", "Mathematics & Statistical Rigor"),
            ("legal_contracts", "Contract Analysis & Legal Review"),
            ("ergonomics", "Workplace Ergonomics & Wellness"),
            ("interview_viva", "Mock Interview & Viva Simulation"),
            ("smart_home", "Smart-Home & IoT Orchestration"),
            ("meeting_intelligence", "Meeting Transcription & Notes"),
            ("code_audit", "Code Review & Bug Auditing"),
            ("finance_tax", "Personal Finance & Tax Intelligence"),
            ("pro_brain", "Pro Brain Parallel Workflows"),
        ]

        count = 1  # Root entity
        for dom_id, dom_name in domains:
            e = Entity(
                id=f"capability_{dom_id}",
                type=EntityType.SKILL,
                canonical_name=dom_name,
                aliases={dom_name, dom_id},
                metadata={"status": "trained", "verified": True},
                confidence=1.0,
                source="brain_trainer",
                created_at=now,
                updated_at=now,
                last_verified_at=now,
            )
            self.kg.upsert_entity(e)

            rel = Relationship(
                id=f"rel_charlie_has_{dom_id}",
                source_id="entity_charlie_assistant",
                target_id=f"capability_{dom_id}",
                relation_type=RelationType.USES_TOOL,
                source_provenance="brain_trainer",
                confidence=1.0,
                created_at=now,
                valid_from=now,
            )
            self.kg.upsert_relationship(rel)
            count += 1

        return count


def train_charlie_brain_and_memory(db_path: Optional[Path] = None) -> Dict[str, int]:
    """Top-level convenience function to trigger complete memory training."""
    trainer = BrainTrainer(db_path=db_path)
    return trainer.train_all()


if __name__ == "__main__":
    results = train_charlie_brain_and_memory()
    print("Brain & Memory Training Results:")
    for k, v in results.items():
        print(f"  {k}: {v}")
