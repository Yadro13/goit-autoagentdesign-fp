"""Contract tests для reused Pydantic tools і sanitized simulator."""

from __future__ import annotations

import json
from pathlib import Path

from tools_legacy import build_tool_registry


def test_registry_exposes_expected_tools(tmp_path: Path) -> None:
    registry = build_tool_registry(tmp_path / "chroma", tmp_path / "safeops.db")
    try:
        assert {tool.name for tool in registry.tools} == {
            "get_system_health",
            "inspect_operations",
            "check_bonus_integrity",
            "search_knowledge",
            "retry_failed_job",
        }
    finally:
        registry.close()


def test_retry_rejects_non_synthetic_job_id(tmp_path: Path) -> None:
    registry = build_tool_registry(tmp_path / "chroma", tmp_path / "safeops.db")
    try:
        result = json.loads(
            registry.invoke(
                "retry_failed_job",
                {
                    "job_id": "PROD-42",
                    "expected_status": "dead",
                    "reason": "synthetic demo",
                    "idempotency_key": "synthetic-42",
                },
            )
        )
        assert result["status"] == "error"
        assert result["error"]["code"] == "validation_error"
    finally:
        registry.close()
