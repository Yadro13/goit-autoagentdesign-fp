"""Async unit tests для FastMCP surface Riverwash SafeOps."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

import pytest

import mcp_server


def _text(result: object) -> str:
    """Витягнути text з direct FastMCP result без transport assumptions."""

    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False)
    if isinstance(result, str):
        return result
    # FastMCP direct call повертає `(content_blocks, structured_content)`.
    if isinstance(result, tuple) and len(result) == 2:
        return _text(result[0])
    if hasattr(result, "text"):
        return str(result.text)
    if hasattr(result, "content"):
        return _text(result.content)
    if hasattr(result, "messages"):
        return _text(result.messages)
    if isinstance(result, Iterable):
        chunks = [_text(item) for item in result]
        return "\n".join(chunks)
    return str(result)


def _payload(result: object) -> dict[str, object]:
    return json.loads(_text(result))


@pytest.fixture(autouse=True)
def isolated_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SAFEOPS_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CHROMA_DB_PATH", raising=False)
    monkeypatch.delenv("SAFEOPS_DB_PATH", raising=False)
    mcp_server.reset_registry()
    yield
    mcp_server.reset_registry()


@pytest.mark.asyncio
async def test_registers_five_documented_tools() -> None:
    tools = await mcp_server.mcp.list_tools()
    assert {tool.name for tool in tools} == {
        "get_system_health",
        "inspect_operations",
        "check_bonus_integrity",
        "search_knowledge",
        "retry_failed_job",
    }
    assert all((tool.description or "").strip() for tool in tools)


@pytest.mark.asyncio
async def test_health_tool_returns_sanitized_snapshot() -> None:
    result = await mcp_server.mcp.call_tool("get_system_health", {})
    payload = _payload(result)
    assert payload["status"] == "ok"
    assert payload["data"]["source"] == "sanitized_standalone_fixture"
    assert "secret" not in _text(result).casefold()


@pytest.mark.asyncio
async def test_invalid_health_input_is_error_envelope() -> None:
    result = await mcp_server.mcp.call_tool(
        "get_system_health", {"component": "unknown", "max_age_seconds": 31}
    )
    payload = _payload(result)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_operations_and_integrity_are_deterministic() -> None:
    operations = _payload(await mcp_server.mcp.call_tool("inspect_operations", {}))
    integrity = _payload(await mcp_server.mcp.call_tool("check_bonus_integrity", {}))
    assert operations["data"]["counts"]["dead"] >= 1
    assert integrity["data"]["violations"] == 1


@pytest.mark.asyncio
async def test_chromadb_knowledge_search_returns_ranked_runbooks() -> None:
    result = await mcp_server.mcp.call_tool(
        "search_knowledge", {"query": "dead job retry idempotency", "top_k": 2}
    )
    payload = _payload(result)
    assert payload["status"] == "ok"
    assert len(payload["data"]["results"]) == 2
    assert payload["data"]["results"][0]["id"].startswith("RB-")


@pytest.mark.asyncio
async def test_risky_tool_is_idempotent_and_validated() -> None:
    args = {
        "job_id": "JOB-SIM-002",
        "expected_status": "dead",
        "reason": "approved synthetic demo retry",
        "idempotency_key": "demo-retry-002",
    }
    first = _payload(await mcp_server.mcp.call_tool("retry_failed_job", args))
    second = _payload(await mcp_server.mcp.call_tool("retry_failed_job", args))
    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert second["data"]["idempotent_replay"] is True


@pytest.mark.asyncio
async def test_read_only_resources_are_registered_and_readable() -> None:
    resources = await mcp_server.mcp.list_resources()
    uris = {str(resource.uri) for resource in resources}
    assert uris == {"safeops://runbooks/catalog", "safeops://status/snapshot"}
    catalog = await mcp_server.mcp.read_resource("safeops://runbooks/catalog")
    assert "RB-001" in _text(catalog)


@pytest.mark.asyncio
async def test_incident_prompt_is_registered_and_enforces_hitl() -> None:
    prompts = await mcp_server.mcp.list_prompts()
    assert {prompt.name for prompt in prompts} == {"incident_brief"}
    rendered = await mcp_server.mcp.get_prompt(
        "incident_brief",
        {"incident_summary": "JOB-SIM-002 is dead", "audience": "operator"},
    )
    text = _text(rendered)
    assert "HITL" in text
    assert "JOB-SIM-002" in text
