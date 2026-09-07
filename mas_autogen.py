"""Bonus: той самий Riverwash SafeOps кейс у Microsoft AutoGen AgentChat.

AutoGen branch is intentionally recommendation-only for remediation. The production
side effect remains in the LangGraph branch where persisted HITL is explicit.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_agentchat.teams import SelectorGroupChat
from autogen_core import CancellationToken
from autogen_core.models import ModelFamily
from autogen_core.tools import ToolResult, ToolSchema, Workbench
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams

from mas_langgraph import PROJECT_ROOT, SYSTEM_PROMPTS
from safeops_core.config import get_settings

AUTOGEN_ALLOWED_TOOLS = {
    "monitor_agent": {"get_system_health", "inspect_operations"},
    "investigator_agent": {
        "get_system_health",
        "inspect_operations",
        "check_bonus_integrity",
        "search_knowledge",
    },
    "researcher_agent": {"search_knowledge"},
    # Recommendation-only branch: no risky side-effect tool is exposed here.
    "remediation_agent": {"inspect_operations", "search_knowledge"},
}


class FilteredMcpWorkbench(Workbench):
    """AutoGen Workbench facade enforcing an actual per-agent MCP allowlist."""

    def __init__(self, inner: McpWorkbench, allowed: set[str]) -> None:
        self.inner = inner
        self.allowed = allowed
        self.started = False

    async def list_tools(self) -> list[ToolSchema]:
        schemas = await self.inner.list_tools()
        self.started = True
        return [schema for schema in schemas if schema["name"] in self.allowed]

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        cancellation_token: CancellationToken | None = None,
        call_id: str | None = None,
    ) -> ToolResult:
        if name not in self.allowed:
            raise PermissionError(f"AutoGen workbench denied tool: {name}")
        result = await self.inner.call_tool(name, arguments, cancellation_token, call_id)
        self.started = True
        return result

    async def start(self) -> None:
        await self.inner.start()
        self.started = True

    async def stop(self) -> None:
        if self.started:
            await self.inner.stop()
            self.started = False

    async def reset(self) -> None:
        await self.inner.reset()

    async def save_state(self) -> Mapping[str, Any]:
        return await self.inner.save_state()

    async def load_state(self, state: Mapping[str, Any]) -> None:
        await self.inner.load_state(state)


def route_task(task: str) -> str:
    """Deterministic selector keeps comparison routing equivalent to LangGraph."""

    lowered = task.casefold()
    has_job = bool(re.search(r"JOB-SIM-\d{3}", task, re.IGNORECASE))
    if has_job and any(word in lowered for word in ("retry", "повтори", "перезапусти")):
        return "remediation_agent"
    if any(word in lowered for word in ("runbook", "політик", "правил", "knowledge", "як діяти")):
        return "researcher_agent"
    if any(word in lowered for word in ("розслід", "incident", "причин", "integrity", "інцидент")):
        return "investigator_agent"
    return "monitor_agent"


def _selector(messages: Any) -> str:
    task = ""
    for message in messages:
        if getattr(message, "source", "") == "user":
            task = str(getattr(message, "content", ""))
            break
    return route_task(task)


def _server_params() -> StdioServerParams:
    settings = get_settings()
    return StdioServerParams(
        command=sys.executable,
        args=[str(PROJECT_ROOT / "mcp_server.py")],
        cwd=PROJECT_ROOT,
        env={
            "SAFEOPS_DATA_DIR": str(settings.data_dir),
            "CHROMA_DB_PATH": str(settings.chroma_path),
            "SAFEOPS_DB_PATH": str(settings.safeops_db_path),
            "PYTHONPATH": str(PROJECT_ROOT),
        },
        read_timeout_seconds=15,
    )


async def run_autogen(task: str) -> dict[str, Any]:
    """Run a one-turn SelectorGroupChat using the same FastMCP server."""

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for the AutoGen bonus demo")
    settings = get_settings()
    autogen_model = (
        "gpt-5.4-mini-2026-03-17" if settings.openai_model == "gpt-5.4-mini" else settings.openai_model
    )
    model_client = OpenAIChatCompletionClient(
        model=autogen_model,
        # AutoGen 0.7.5 uses Chat Completions; GPT-5.4 Mini tool calls there
        # require reasoning_effort="none" (Responses API supports reasoning).
        reasoning_effort="none",
        model_info={
            "vision": True,
            "function_calling": True,
            "json_output": True,
            "family": ModelFamily.GPT_5,
            "structured_output": True,
            "multiple_system_messages": True,
        },
    )
    workbenches = {
        name: FilteredMcpWorkbench(McpWorkbench(_server_params()), allowed)
        for name, allowed in AUTOGEN_ALLOWED_TOOLS.items()
    }
    agents = [
        AssistantAgent(
            "monitor_agent",
            model_client=model_client,
            description="Current health and queues",
            system_message=SYSTEM_PROMPTS["monitor"] + " End with TERMINATE.",
            workbench=workbenches["monitor_agent"],
            reflect_on_tool_use=True,
            max_tool_iterations=3,
        ),
        AssistantAgent(
            "investigator_agent",
            model_client=model_client,
            description="Multi-source incident investigation",
            system_message=(
                SYSTEM_PROMPTS["investigator"]
                + " Execute a short plan with the available MCP tools, then end with TERMINATE."
            ),
            workbench=workbenches["investigator_agent"],
            reflect_on_tool_use=True,
            max_tool_iterations=5,
        ),
        AssistantAgent(
            "researcher_agent",
            model_client=model_client,
            description="ChromaDB runbook research",
            system_message=SYSTEM_PROMPTS["researcher"] + " End with TERMINATE.",
            workbench=workbenches["researcher_agent"],
            reflect_on_tool_use=True,
            max_tool_iterations=3,
        ),
        AssistantAgent(
            "remediation_agent",
            model_client=model_client,
            description="Recommendation-only remediation proposal",
            system_message=(
                SYSTEM_PROMPTS["remediation"]
                + " In this comparison branch, propose only; the risky tool is not exposed. "
                "End with TERMINATE."
            ),
            workbench=workbenches["remediation_agent"],
            reflect_on_tool_use=True,
            max_tool_iterations=3,
        ),
    ]
    team = SelectorGroupChat(
        agents,
        model_client=model_client,
        selector_func=_selector,
        termination_condition=MaxMessageTermination(2),
        max_turns=1,
        emit_team_events=True,
    )
    started = time.perf_counter()
    try:
        result = await team.run(task=task)
        messages = [
            {
                "source": getattr(message, "source", type(message).__name__),
                "content": str(getattr(message, "content", "")),
            }
            for message in result.messages
        ]
        usage = {
            "prompt_tokens": sum(
                getattr(getattr(message, "models_usage", None), "prompt_tokens", 0) or 0
                for message in result.messages
            ),
            "completion_tokens": sum(
                getattr(getattr(message, "models_usage", None), "completion_tokens", 0) or 0
                for message in result.messages
            ),
        }
        return {
            "framework": "AutoGen AgentChat",
            "selected_agent": route_task(task),
            "messages": messages,
            "usage": usage,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    finally:
        await team.reset()
        for workbench in workbenches.values():
            await workbench.stop()
        await model_client.close()


async def demo() -> None:
    examples = [
        "Перевір health і queue воркерів",
        "Розслідуй incident bonus projection та integrity",
        "Знайди runbook щодо idempotent retry і HITL",
    ]
    results = [await run_autogen(example) for example in examples]
    output = Path(__file__).with_name("autogen_demo_results.json")
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoGen bonus implementation")
    parser.add_argument("query", nargs="?")
    args = parser.parse_args()
    if args.query:
        print(json.dumps(asyncio.run(run_autogen(args.query)), ensure_ascii=False, indent=2))
    else:
        asyncio.run(demo())


if __name__ == "__main__":
    main()
