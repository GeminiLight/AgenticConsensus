from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from system.domain.models import new_id


AIFeature = Literal[
    "review_copilot",
    "intent_interpreter",
    "evidence_gap_planner",
    "commitment_draft",
    "risk_analysis",
]


class EvidenceContextCard(BaseModel):
    id: str = Field(min_length=1, max_length=300)
    kind: Literal[
        "review",
        "claim",
        "evidence",
        "finding",
        "obligation",
        "admission_check",
        "decision",
        "diff",
    ]
    label: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=8000)
    status: str = Field(default="unknown", max_length=120)


class AICitation(BaseModel):
    id: str
    kind: str
    label: str
    excerpt: str = Field(max_length=1200)


class ReviewAIContext(BaseModel):
    project_id: str
    review_id: str
    review_revision: int = Field(ge=1)
    project_version: int = Field(ge=1)
    cards: list[EvidenceContextCard]
    context_hash: str = Field(min_length=64, max_length=64)


class AIFeedback(BaseModel):
    run_id: str
    verdict: Literal["accepted", "edited", "rejected"]
    actor: str = Field(min_length=1, max_length=200)
    note: str = Field(default="", max_length=4000)
    edited_response: str | None = Field(default=None, max_length=12000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("actor", mode="before")
    @classmethod
    def normalize_actor(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("feedback actor must not be blank")
        return normalized

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_edited_response(self):
        if self.verdict == "edited":
            if self.edited_response is None or not self.edited_response.strip():
                raise ValueError("edited feedback requires the edited response")
            self.edited_response = self.edited_response.strip()
        elif self.edited_response is not None:
            raise ValueError("only edited feedback may include an edited response")
        return self


class AIAdvisoryRun(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ai-run"))
    project_id: str
    review_id: str | None = None
    project_version: int = Field(ge=1)
    review_revision: int | None = Field(default=None, ge=1)
    intent_id: str | None = None
    feature: AIFeature
    request: str = Field(min_length=1, max_length=12000)
    result: dict[str, Any]
    citations: list[AICitation] = Field(default_factory=list, max_length=100)
    uncertainties: list[str] = Field(default_factory=list, max_length=50)
    suggested_checks: list[str] = Field(default_factory=list, max_length=50)
    source: Literal["model", "deterministic", "hybrid"]
    provider: str
    model: str | None = None
    prompt_version: str = Field(min_length=1, max_length=120)
    context_hash: str = Field(min_length=64, max_length=64)
    latency_ms: int = Field(default=0, ge=0)
    usage: dict[str, int] = Field(default_factory=dict)
    grounded: bool
    citation_precision: float = Field(ge=0, le=1)
    faithfulness_score: float = Field(ge=0, le=1)
    quality_flags: list[str] = Field(default_factory=list, max_length=30)
    feedback: AIFeedback | None = None
    created_by: str = Field(min_length=1, max_length=200)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AIEvalSummary(BaseModel):
    runs: int = Field(ge=0)
    grounded_rate: float = Field(ge=0, le=1)
    mean_citation_precision: float = Field(ge=0, le=1)
    mean_faithfulness: float = Field(ge=0, le=1)
    fallback_rate: float = Field(ge=0, le=1)
    average_latency_ms: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    feedback: dict[Literal["accepted", "edited", "rejected"], int]
    acceptance_rate: float = Field(ge=0, le=1)
