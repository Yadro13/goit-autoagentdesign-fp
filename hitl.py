"""HITL demo: persisted interrupt -> simulated crash -> Command(resume=...)."""

from __future__ import annotations

import argparse
import json
import uuid
from typing import Any

from mas_langgraph import SafeOpsMAS
from safeops_core.config import get_settings


def run_persistence_demo(
    decision: dict[str, Any],
    *,
    use_mcp: bool = True,
    live_llm: bool = False,
) -> dict[str, Any]:
    """Persist approval request, close runtime, then resume from the same thread id."""

    settings = get_settings()
    thread_id = f"hitl-{uuid.uuid4().hex[:10]}"
    first_runtime = SafeOpsMAS(settings, live_llm=live_llm, use_mcp=use_mcp)
    try:
        interrupted = first_runtime.run(
            "Виконай retry для JOB-SIM-002",
            thread_id=thread_id,
            session_id="hitl-demo",
        )
        if "__interrupt__" not in interrupted:
            raise RuntimeError("Expected LangGraph interrupt was not persisted")
    finally:
        # Це моделює process crash/restart: in-memory runtime повністю знищено.
        first_runtime.close()

    restored_runtime = SafeOpsMAS(settings, live_llm=live_llm, use_mcp=use_mcp)
    try:
        resumed = restored_runtime.resume(thread_id, decision)
        return {
            "thread_id": thread_id,
            "interrupted": True,
            "decision": decision,
            "answer": resumed.get("answer"),
            "approval": resumed.get("approval"),
            "tools_called": resumed.get("tools_called", []),
        }
    finally:
        restored_runtime.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="SafeOps persisted HITL demo")
    parser.add_argument("decision", choices=["approve", "reject", "edit"])
    parser.add_argument("--legacy-tools", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    decision: dict[str, Any] = {"action": args.decision, "reason": "operator CLI demo"}
    if args.decision == "edit":
        decision["args"] = {
            "job_id": "JOB-SIM-002",
            "expected_status": "dead",
            "reason": "operator edited synthetic demo retry",
            "idempotency_key": f"edited-demo-{uuid.uuid4().hex[:12]}",
        }
    result = run_persistence_demo(
        decision,
        use_mcp=not args.legacy_tools,
        live_llm=args.live,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    get_settings().project_root.joinpath("hitl_demo_result.json").write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
