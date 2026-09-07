"""LangSmith configuration та privacy-safe local observability summary."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from safeops_core.config import get_settings


def configure_langsmith(project: str = "riverwash-safeops-mas") -> dict[str, Any]:
    """Enable LangSmith only when a key is provided by the runtime environment."""

    # Loads `.env.local` without ever returning or logging secret values.
    get_settings()
    enabled = bool(os.getenv("LANGSMITH_API_KEY"))
    if enabled:
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGSMITH_PROJECT", project)
    return {
        "provider": "LangSmith",
        "enabled": enabled,
        "project": os.getenv("LANGSMITH_PROJECT", project),
        "key_present": enabled,
        "key_value_exposed": False,
    }


def local_trajectory_summary(path: Path | None = None) -> dict[str, Any]:
    """Aggregate local traces without exposing raw production payloads."""

    selected = path or get_settings().trajectory_path
    if not selected.exists():
        return {"events": 0, "agents": {}, "nodes": {}, "mean_duration_ms": 0.0}
    rows = json.loads(selected.read_text(encoding="utf-8"))
    durations = [float(row.get("duration_ms", 0)) for row in rows]
    return {
        "events": len(rows),
        "agents": dict(Counter(row.get("agent_name", "unknown") for row in rows)),
        "nodes": dict(Counter(row.get("node", "unknown") for row in rows)),
        "mean_duration_ms": round(sum(durations) / max(1, len(durations)), 3),
    }


if __name__ == "__main__":
    print(
        json.dumps(
            {"langsmith": configure_langsmith(), "local": local_trajectory_summary()},
            ensure_ascii=False,
            indent=2,
        )
    )
