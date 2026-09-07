"""Перевикористані Pydantic v2 tools і Agentic RAG з HW3."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool, tool
from pydantic import ValidationError

from safeops_core.knowledge import KnowledgeBase
from safeops_core.schemas import (
    HealthInput,
    InspectOperationsInput,
    IntegrityCheckInput,
    RetryFailedJobInput,
    SearchKnowledgeInput,
)
from safeops_core.simulator import SafeOpsSimulator

RISKY_TOOLS = {"retry_failed_job"}


def ok(data: Any) -> str:
    return json.dumps({"status": "ok", "data": data}, ensure_ascii=False, indent=2)


def error(code: str, message: str) -> str:
    return json.dumps(
        {"status": "error", "error": {"code": code, "message": message}}, ensure_ascii=False, indent=2
    )


@dataclass(slots=True)
class ToolRegistry:
    """Transport-neutral tool registry; той самий backend використовує FastMCP."""

    knowledge: KnowledgeBase
    simulator: SafeOpsSimulator
    tools: list[BaseTool]

    @property
    def by_name(self) -> dict[str, BaseTool]:
        return {item.name: item for item in self.tools}

    def invoke(self, name: str, args: dict[str, Any]) -> str:
        selected = self.by_name.get(name)
        if selected is None:
            return error("unknown_tool", f"Невідомий tool '{name}'")
        try:
            result = selected.invoke(args)
            return result if isinstance(result, str) else ok(result)
        except (ValidationError, ValueError, TypeError) as exc:
            return error("validation_error", str(exc))

    def close(self) -> None:
        self.simulator.close()


def build_tool_registry(chroma_path: Path, safeops_db_path: Path) -> ToolRegistry:
    knowledge = KnowledgeBase(chroma_path)
    simulator = SafeOpsSimulator(safeops_db_path)

    @tool(args_schema=HealthInput)
    def get_system_health(component: str = "all", max_age_seconds: int = 300) -> str:
        """Отримати readiness і heartbeat freshness санітизованих Riverwash-компонентів.

        Використовуйте для актуального стану, а не історичних правил. Tool read-only;
        він не повертає credentials, customer PII або production topology.
        """

        return ok(simulator.health(component, max_age_seconds))

    @tool(args_schema=InspectOperationsInput)
    def inspect_operations(
        component: str = "all", window_minutes: int = 60, include_recovered: bool = True
    ) -> str:
        """Перевірити pending/retry/dead jobs та безпечні класи помилок за часовим вікном.

        Відповідь містить лише sanitized identifiers, агрегати та error categories.
        """

        return ok(simulator.operations(component, include_recovered, window_minutes))

    @tool(args_schema=IntegrityCheckInput)
    def check_bonus_integrity(scope: str = "all", sample_limit: int = 1000) -> str:
        """Детерміновано перевірити ledger, balance/reserved та projection інваріанти.

        LLM не обчислює фінансові інваріанти самостійно; tool повертає результат коду.
        """

        return ok(simulator.integrity(scope, sample_limit))

    @tool(args_schema=SearchKnowledgeInput)
    def search_knowledge(query: str, top_k: int = 3) -> str:
        """Виконати Agentic RAG пошук у ChromaDB за sanitized SafeOps runbooks.

        Використовуйте для recovery policy, severity, privacy, migration або HITL;
        не використовуйте замість актуальних health/queue фактів.
        """

        return ok({"query": query, "results": knowledge.search(query, top_k)})

    @tool(args_schema=RetryFailedJobInput)
    def retry_failed_job(job_id: str, expected_status: str, reason: str, idempotency_key: str) -> str:
        """Повторити рівно одну sanitized failed job після HITL approval.

        Це ризикова side-effect дія. Вона має optimistic precondition та idempotency
        key, працює лише з `JOB-SIM-*` і ніколи не торкається production Riverwash.
        """

        payload = RetryFailedJobInput(
            job_id=job_id,
            expected_status=expected_status,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        return json.dumps(simulator.retry_job(**payload.model_dump()), ensure_ascii=False, indent=2)

    return ToolRegistry(
        knowledge=knowledge,
        simulator=simulator,
        tools=[
            get_system_health,
            inspect_operations,
            check_bonus_integrity,
            search_knowledge,
            retry_failed_job,
        ],
    )
