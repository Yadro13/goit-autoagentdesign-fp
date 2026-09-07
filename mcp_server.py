"""FastMCP server Riverwash SafeOps: tools, resources та prompt.

Запуск через stdio: `python mcp_server.py`. У stdout не пишуться логи, бо це
пошкодило б MCP JSON-RPC transport.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from safeops_core.knowledge import RUNBOOKS
from tools_legacy import ToolRegistry, build_tool_registry, error

PROJECT_ROOT = Path(__file__).resolve().parent
mcp = FastMCP(
    name="riverwash-safeops",
    instructions=(
        "Sanitized SafeOps server for health, operations, integrity, runbooks and one "
        "HITL-protected remediation action. Never assume access to production secrets."
    ),
)

_registry: ToolRegistry | None = None
_registry_key: tuple[str, str] | None = None
_registry_lock = threading.Lock()


def _paths() -> tuple[Path, Path]:
    data_dir = Path(os.getenv("SAFEOPS_DATA_DIR", PROJECT_ROOT)).resolve()
    return (
        Path(os.getenv("CHROMA_DB_PATH", data_dir / "chroma_db")),
        Path(os.getenv("SAFEOPS_DB_PATH", data_dir / "safeops.db")),
    )


def get_registry() -> ToolRegistry:
    """Ліниво створити backend і перебудувати його після зміни test paths."""

    global _registry, _registry_key
    chroma_path, db_path = _paths()
    key = (str(chroma_path.resolve()), str(db_path.resolve()))
    with _registry_lock:
        if _registry is None or _registry_key != key:
            if _registry is not None:
                _registry.close()
            _registry = build_tool_registry(chroma_path, db_path)
            _registry_key = key
        return _registry


def reset_registry() -> None:
    """Закрити cached backend; використовується ізольованими unit tests."""

    global _registry, _registry_key
    with _registry_lock:
        if _registry is not None:
            _registry.close()
        _registry = None
        _registry_key = None


@mcp.tool()
def get_system_health(component: str = "all", max_age_seconds: int = 300) -> str:
    """Отримати sanitized readiness та heartbeat freshness.

    Args:
        component: `all` або дозволене ім'я Riverwash-компонента.
        max_age_seconds: Heartbeat TTL від 30 до 3600, кратний 10.
    Returns:
        JSON envelope зі status та безпечними health facts. Validation errors також
        повертаються стандартним error envelope, а не аварійно завершують server.
    """

    try:
        return get_registry().invoke(
            "get_system_health", {"component": component, "max_age_seconds": max_age_seconds}
        )
    except Exception as exc:  # MCP boundary має перетворити unexpected backend error
        return error("health_failed", type(exc).__name__)


@mcp.tool()
def inspect_operations(
    component: str = "all", window_minutes: int = 60, include_recovered: bool = True
) -> str:
    """Перевірити sanitized pending/retry/dead jobs і класи помилок.

    Args:
        component: `all` або один дозволений компонент.
        window_minutes: Стандартне вікно 5..1440 хвилин.
        include_recovered: Чи включати вже відновлені події.
    Returns:
        JSON envelope з counts та sanitized job metadata без raw payload/PII.
    """

    try:
        return get_registry().invoke(
            "inspect_operations",
            {
                "component": component,
                "window_minutes": window_minutes,
                "include_recovered": include_recovered,
            },
        )
    except Exception as exc:
        return error("operations_failed", type(exc).__name__)


@mcp.tool()
def check_bonus_integrity(scope: str = "all", sample_limit: int = 1000) -> str:
    """Детерміновано перевірити sanitized bonus ledger/projection інваріанти.

    Args:
        scope: `accounts`, `ledger`, `projections` або `all`.
        sample_limit: Розмір вибірки 10..10000.
    Returns:
        JSON envelope з кількістю порушень; LLM не виконує фінансові обчислення.
    """

    try:
        return get_registry().invoke("check_bonus_integrity", {"scope": scope, "sample_limit": sample_limit})
    except Exception as exc:
        return error("integrity_failed", type(exc).__name__)


@mcp.tool()
def search_knowledge(query: str, top_k: int = 3) -> str:
    """Знайти sanitized SafeOps recovery/security правила у ChromaDB.

    Args:
        query: Питання без secrets або customer PII.
        top_k: Від одного до п'яти runbooks.
    Returns:
        JSON envelope з ranked knowledge chunks та scores.
    """

    try:
        return get_registry().invoke("search_knowledge", {"query": query, "top_k": top_k})
    except Exception as exc:
        return error("knowledge_failed", type(exc).__name__)


@mcp.tool()
def retry_failed_job(job_id: str, expected_status: str, reason: str, idempotency_key: str) -> str:
    """Повторити рівно одну sanitized job після зовнішнього HITL approval.

    Args:
        job_id: Лише `JOB-SIM-NNN`; production identifiers не приймаються.
        expected_status: Optimistic precondition `dead` або `retry`.
        reason: Audit reason із маркером `demo`, `тест` або `synthetic`.
        idempotency_key: Стабільний lowercase ключ 8..64 символів.
    Returns:
        JSON envelope з remediation id або детермінованою validation/stale error.
    Security:
        Tool є ризиковим. MCP server валідовує контракт, але approval забезпечує
        MAS до виклику; прямий client не отримує production-доступу.
    """

    try:
        return get_registry().invoke(
            "retry_failed_job",
            {
                "job_id": job_id,
                "expected_status": expected_status,
                "reason": reason,
                "idempotency_key": idempotency_key,
            },
        )
    except Exception as exc:
        return error("retry_failed", type(exc).__name__)


@mcp.resource("safeops://runbooks/catalog", mime_type="application/json")
def runbook_catalog() -> str:
    """Read-only каталог sanitized runbooks без внутрішнього production content."""

    return json.dumps(
        [{"id": item["id"], "topic": item["topic"], "summary": item["text"]} for item in RUNBOOKS],
        ensure_ascii=False,
        indent=2,
    )


@mcp.resource("safeops://status/snapshot", mime_type="application/json")
def status_snapshot() -> str:
    """Read-only snapshot health та operations для host-controlled context loading."""

    registry = get_registry()
    return json.dumps(
        {
            "health": json.loads(registry.invoke("get_system_health", {})),
            "operations": json.loads(registry.invoke("inspect_operations", {})),
            "commercial_data_included": False,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.prompt()
def incident_brief(incident_summary: str, audience: str = "operator") -> str:
    """Створити стандартизований prompt для evidence-based incident brief.

    Args:
        incident_summary: Sanitized факти інциденту.
        audience: `operator`, `manager` або `engineer`.
    """

    return (
        f"Підготуй українською SafeOps brief для {audience}. Факти: {incident_summary}. "
        "Відокрем активний стан від історії, наведи evidence, ризик, безпечний наступний крок "
        "та познач будь-яку side-effect дію як таку, що потребує HITL. Не вигадуй production details."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
