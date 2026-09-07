"""Sanitized contract-equivalent backend для відтворюваної SafeOps здачі."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

COMPONENTS: list[dict[str, Any]] = [
    {"name": "crm_webhook_worker", "ready": True, "heartbeat_age_seconds": 42},
    {"name": "bonus_side_effect_worker", "ready": True, "heartbeat_age_seconds": 37},
    {"name": "bonus_projection_worker", "ready": True, "heartbeat_age_seconds": 55},
    {"name": "scheduler", "ready": True, "heartbeat_age_seconds": 71},
    {"name": "order_status_notifier", "ready": True, "heartbeat_age_seconds": 29},
]

JOBS: list[dict[str, Any]] = [
    {"job_id": "JOB-SIM-001", "component": "crm_webhook_worker", "status": "done", "attempts": 1},
    {
        "job_id": "JOB-SIM-002",
        "component": "bonus_projection_worker",
        "status": "dead",
        "attempts": 4,
        "error_kind": "UpstreamTimeout",
        "http_status": 504,
        "endpoint_class": "bonus_projection_write",
        "recovered": False,
    },
    {
        "job_id": "JOB-SIM-003",
        "component": "order_status_notifier",
        "status": "done",
        "attempts": 2,
        "error_kind": "TerminalRecipientError",
        "endpoint_class": "notification_send",
        "recovered": True,
    },
]

INTEGRITY = {
    "accounts_checked": 560,
    "negative_balances": 0,
    "reserved_exceeds_balance": 0,
    "outcomes_without_ledger": 0,
    "stuck_projections": 1,
}


@dataclass(slots=True)
class SafeOpsSimulator:
    """SQLite backend із persistent job state та exactly-once remediation ledger."""

    path: Path
    _connection: sqlite3.Connection = field(init=False, repr=False)
    _lock: threading.Lock = field(init=False, repr=False, default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS job_states (
                   job_id TEXT PRIMARY KEY, status TEXT NOT NULL
               )"""
        )
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS remediations (
                   remediation_id TEXT PRIMARY KEY,
                   idempotency_key TEXT NOT NULL UNIQUE,
                   job_id TEXT NOT NULL,
                   previous_status TEXT NOT NULL,
                   new_status TEXT NOT NULL,
                   reason TEXT NOT NULL,
                   created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
               )"""
        )
        self._connection.executemany(
            "INSERT OR IGNORE INTO job_states(job_id,status) VALUES (?,?)",
            [(item["job_id"], item["status"]) for item in JOBS],
        )
        self._connection.commit()

    def health(self, component: str, max_age_seconds: int) -> dict[str, Any]:
        selected = COMPONENTS if component == "all" else [x for x in COMPONENTS if x["name"] == component]
        items = [
            {**item, "healthy": bool(item["ready"] and item["heartbeat_age_seconds"] <= max_age_seconds)}
            for item in selected
        ]
        return {
            "overall": "healthy" if items and all(x["healthy"] for x in items) else "degraded",
            "components": items,
            "source": "sanitized_standalone_fixture",
        }

    def operations(self, component: str, include_recovered: bool, window_minutes: int) -> dict[str, Any]:
        statuses = dict(self._connection.execute("SELECT job_id,status FROM job_states").fetchall())
        rows: list[dict[str, Any]] = []
        for item in JOBS:
            if component != "all" and item["component"] != component:
                continue
            if item.get("recovered") and not include_recovered:
                continue
            rows.append({**item, "status": statuses[item["job_id"]]})
        counts = {
            status: sum(row["status"] == status for row in rows) for status in ("done", "retry", "dead")
        }
        return {"counts": counts, "jobs": rows, "window_minutes": window_minutes, "pii_redacted": True}

    def integrity(self, scope: str, sample_limit: int) -> dict[str, Any]:
        data = {**INTEGRITY, "scope": scope, "sample_limit": sample_limit}
        data["violations"] = sum(
            data[key]
            for key in (
                "negative_balances",
                "reserved_exceeds_balance",
                "outcomes_without_ledger",
                "stuck_projections",
            )
        )
        return data

    def retry_job(
        self, *, job_id: str, expected_status: str, reason: str, idempotency_key: str
    ) -> dict[str, Any]:
        with self._lock:
            existing = self._connection.execute(
                "SELECT remediation_id,job_id,new_status FROM remediations WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                return {
                    "status": "ok",
                    "data": {
                        "remediation_id": existing[0],
                        "job_id": existing[1],
                        "new_status": existing[2],
                        "idempotent_replay": True,
                    },
                }
            row = self._connection.execute(
                "SELECT status FROM job_states WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                return {"status": "error", "error": {"code": "job_not_found", "message": "Job не знайдено"}}
            current = str(row[0])
            if current != expected_status:
                return {
                    "status": "error",
                    "error": {
                        "code": "stale_status",
                        "message": f"Очікувався {expected_status}, фактичний {current}",
                    },
                }
            remediation_id = (
                "REM-" + hashlib.sha256(f"{job_id}:{idempotency_key}".encode()).hexdigest()[:10].upper()
            )
            self._connection.execute("UPDATE job_states SET status='retry' WHERE job_id=?", (job_id,))
            self._connection.execute(
                """INSERT INTO remediations
                   (remediation_id,idempotency_key,job_id,previous_status,new_status,reason)
                   VALUES (?,?,?,?,?,?)""",
                (remediation_id, idempotency_key, job_id, current, "retry", reason),
            )
            self._connection.commit()
            return {
                "status": "ok",
                "data": {
                    "remediation_id": remediation_id,
                    "job_id": job_id,
                    "previous_status": current,
                    "new_status": "retry",
                    "idempotent_replay": False,
                },
            }

    @property
    def remediation_count(self) -> int:
        return int(self._connection.execute("SELECT COUNT(*) FROM remediations").fetchone()[0])

    def reset(self) -> None:
        with self._lock:
            self._connection.execute("DELETE FROM remediations")
            self._connection.execute("DELETE FROM job_states")
            self._connection.executemany(
                "INSERT INTO job_states(job_id,status) VALUES (?,?)",
                [(item["job_id"], item["status"]) for item in JOBS],
            )
            self._connection.commit()

    def close(self) -> None:
        self._connection.close()
