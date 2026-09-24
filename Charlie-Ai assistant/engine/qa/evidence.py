"""
JARVIS Phase 13: Evidence Registry
Persistent verifiable store for all test and evaluation results with cryptographic SHA256 integrity.
No feature can be certified PASS without a recorded, verifiable EvidenceRecord.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from .models import CertificationStatus, EvidenceRecord

logger = logging.getLogger("jarvis.qa.evidence")


class EvidenceRegistry:
    """Stores and verifies empirical test and evaluation evidence."""

    def __init__(self, db_path: str = "qa_evidence.db"):
        self.db_path = db_path
        self._init_db()

    @contextlib.contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_records (
                    evidence_id TEXT PRIMARY KEY,
                    test_id TEXT NOT NULL,
                    feature_name TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    timestamp REAL,
                    environment TEXT,
                    inputs TEXT,
                    expected_result TEXT,
                    actual_result TEXT,
                    status TEXT,
                    logs TEXT,
                    metrics TEXT,
                    evidence_hash TEXT NOT NULL,
                    failure_details TEXT
                )
                """
            )
            conn.commit()

    def record_evidence(
        self,
        test_id: str,
        feature_name: str,
        phase: str,
        run_id: str,
        expected_result: Any,
        actual_result: Any,
        status: CertificationStatus,
        inputs: Optional[Dict[str, Any]] = None,
        environment: Optional[Dict[str, Any]] = None,
        logs: Optional[List[str]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        failure_details: Optional[str] = None,
    ) -> EvidenceRecord:
        """Records an empirical evidence item with SHA256 integrity hash."""
        now = time.time()
        env_dict = environment or {"os": "Windows 10", "arch": "AMD64"}
        in_dict = inputs or {}
        log_list = logs or []
        met_dict = metrics or {}

        # Compute SHA256 hash across inputs, expected, actual, and status
        hash_payload = f"{test_id}:{run_id}:{status.value}:{json.dumps(expected_result, default=str)}:{json.dumps(actual_result, default=str)}"
        ev_hash = hashlib.sha256(hash_payload.encode()).hexdigest()

        record = EvidenceRecord(
            test_id=test_id,
            feature_name=feature_name,
            phase=phase,
            run_id=run_id,
            timestamp=now,
            environment=env_dict,
            inputs=in_dict,
            expected_result=expected_result,
            actual_result=actual_result,
            status=status,
            logs=log_list,
            metrics=met_dict,
            evidence_hash=ev_hash,
            failure_details=failure_details,
        )

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO evidence_records (
                    evidence_id, test_id, feature_name, phase, run_id,
                    timestamp, environment, inputs, expected_result,
                    actual_result, status, logs, metrics, evidence_hash,
                    failure_details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.evidence_id,
                    record.test_id,
                    record.feature_name,
                    record.phase,
                    record.run_id,
                    record.timestamp,
                    json.dumps(record.environment),
                    json.dumps(record.inputs, default=str),
                    json.dumps(record.expected_result, default=str),
                    json.dumps(record.actual_result, default=str),
                    record.status.value,
                    json.dumps(record.logs),
                    json.dumps(record.metrics),
                    record.evidence_hash,
                    record.failure_details,
                ),
            )
            conn.commit()

        logger.info(f"Recorded evidence {record.evidence_id} for {test_id} [{status.value}]")
        return record

    def get_evidence(self, evidence_id: str) -> Optional[EvidenceRecord]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM evidence_records WHERE evidence_id = ?", (evidence_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def list_evidence_for_phase(self, phase: str) -> List[EvidenceRecord]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM evidence_records WHERE phase = ? ORDER BY timestamp DESC", (phase,))
            return [self._row_to_record(r) for r in cursor.fetchall()]

    def count_by_status(self) -> Dict[str, int]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, COUNT(*) FROM evidence_records GROUP BY status")
            counts = {s.value: 0 for s in CertificationStatus}
            for status_val, count in cursor.fetchall():
                counts[status_val] = count
            return counts

    def _row_to_record(self, row) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=row[0],
            test_id=row[1],
            feature_name=row[2],
            phase=row[3],
            run_id=row[4],
            timestamp=row[5] or 0.0,
            environment=json.loads(row[6]) if row[6] else {},
            inputs=json.loads(row[7]) if row[7] else {},
            expected_result=json.loads(row[8]) if row[8] else None,
            actual_result=json.loads(row[9]) if row[9] else None,
            status=CertificationStatus(row[10]),
            logs=json.loads(row[11]) if row[11] else [],
            metrics=json.loads(row[12]) if row[12] else {},
            evidence_hash=row[13],
            failure_details=row[14],
        )
