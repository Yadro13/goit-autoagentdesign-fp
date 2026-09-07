"""Pydantic v2 контракти MAS, tools, planning, HITL та оцінювання."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

AgentName = Literal["monitor", "investigator", "researcher", "remediation", "general"]
ComponentName = Literal[
    "all",
    "crm_webhook_worker",
    "bonus_side_effect_worker",
    "bonus_projection_worker",
    "scheduler",
    "order_status_notifier",
]


class RouteDecision(BaseModel):
    """Структуроване рішення supervisor про наступного агента."""

    action: AgentName
    reasoning: str = Field(min_length=3, max_length=400)

    @field_validator("reasoning")
    @classmethod
    def normalize_reasoning(cls, value: str) -> str:
        return " ".join(value.split())


class HealthInput(BaseModel):
    component: ComponentName = "all"
    max_age_seconds: int = Field(default=300, ge=30, le=3600)

    @field_validator("max_age_seconds")
    @classmethod
    def round_age(cls, value: int) -> int:
        if value % 10:
            raise ValueError("max_age_seconds має бути кратним 10")
        return value


class InspectOperationsInput(BaseModel):
    component: ComponentName = "all"
    window_minutes: int = Field(default=60, ge=5, le=1440)
    include_recovered: bool = True

    @field_validator("window_minutes")
    @classmethod
    def standard_window(cls, value: int) -> int:
        if value not in {5, 15, 30, 60, 180, 360, 720, 1440}:
            raise ValueError("Використайте стандартне діагностичне вікно")
        return value


class IntegrityCheckInput(BaseModel):
    scope: Literal["accounts", "ledger", "projections", "all"] = "all"
    sample_limit: int = Field(default=1000, ge=10, le=10_000)


class SearchKnowledgeInput(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=3, ge=1, le=5)

    @field_validator("query")
    @classmethod
    def safe_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if re.search(r"\b(?:sk-|AIza|AQ\.)[A-Za-z0-9_-]+", normalized):
            raise ValueError("Секрети не можна передавати у knowledge search")
        return normalized


class RetryFailedJobInput(BaseModel):
    job_id: str = Field(pattern=r"^JOB-SIM-\d{3}$")
    expected_status: Literal["dead", "retry"]
    reason: str = Field(min_length=8, max_length=240)
    idempotency_key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{7,63}$")

    @field_validator("reason")
    @classmethod
    def educational_scope(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not any(marker in normalized.casefold() for marker in ("demo", "тест", "synthetic")):
            raise ValueError("Standalone action reason має містити demo, тест або synthetic")
        return normalized


class PlanStep(BaseModel):
    tool: Literal["get_system_health", "inspect_operations", "check_bonus_integrity", "search_knowledge"]
    purpose: str = Field(min_length=3, max_length=240)
    args: dict[str, object] = Field(default_factory=dict)


class InvestigationPlan(BaseModel):
    goal: str = Field(min_length=5, max_length=300)
    steps: list[PlanStep] = Field(min_length=1, max_length=8)


class ReplanDecision(BaseModel):
    action: Literal["continue", "finish"]
    reasoning: str = Field(min_length=3, max_length=400)
    final_answer: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def finish_requires_answer(self) -> ReplanDecision:
        if self.action == "finish" and not (self.final_answer or "").strip():
            raise ValueError("finish потребує final_answer")
        return self


class RemediationProposal(BaseModel):
    tool: Literal["retry_failed_job"] = "retry_failed_job"
    args: RetryFailedJobInput
    rationale: str = Field(min_length=5, max_length=500)


class ApprovalDecision(BaseModel):
    action: Literal["approve", "reject", "edit"]
    reason: str = Field(default="", max_length=300)
    args: dict[str, object] | None = None

    @model_validator(mode="after")
    def edit_requires_args(self) -> ApprovalDecision:
        if self.action == "edit" and not self.args:
            raise ValueError("edit потребує повний args payload")
        return self


class ScenarioResult(BaseModel):
    scenario_id: str
    query: str
    expected_behavior: str
    actual: str
    passed: bool = Field(alias="pass")
    latency_ms: float
    agents_used: list[str]
    tools_called: list[str]

    model_config = {"populate_by_name": True}
