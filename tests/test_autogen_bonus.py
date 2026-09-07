"""Offline contract tests for the AutoGen comparison branch."""

from mas_autogen import AUTOGEN_ALLOWED_TOOLS, route_task


def test_autogen_selector_routes_same_roles() -> None:
    assert route_task("Перевір health") == "monitor_agent"
    assert route_task("Знайди runbook") == "researcher_agent"
    assert route_task("Розслідуй incident") == "investigator_agent"
    assert route_task("retry JOB-SIM-002") == "remediation_agent"


def test_autogen_remediation_workbench_cannot_execute_side_effect() -> None:
    assert "retry_failed_job" not in AUTOGEN_ALLOWED_TOOLS["remediation_agent"]
    assert "search_knowledge" in AUTOGEN_ALLOWED_TOOLS["remediation_agent"]
