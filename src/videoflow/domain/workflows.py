"""Markdown workflow definitions for the OpenCode Diretor Lego profile."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

WORKFLOW_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
WORKFLOW_EXPORT_TARGETS = ("mp4_youtube", "resolve", "premiere", "kdenlive")


class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=80)
    node: str = Field(min_length=1, max_length=80)
    purpose: str = ""
    requires_approval: bool = False
    params: dict[str, Any] = Field(default_factory=dict)


class WorkflowDefinition(BaseModel):
    """One workflow file under ``{data}/workflows/<workflow_id>.md``."""

    model_config = ConfigDict(extra="allow")

    schema_version: int = Field(default=1, ge=1, le=1)
    version: int = Field(default=1, ge=1)
    workflow_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    aspect_ratio: str = Field(default="16:9", max_length=20)
    platforms: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    steps: list[WorkflowStep] = Field(default_factory=list)
    approvals: list[str] = Field(default_factory=list)
    default_style: str = ""
    compatible_styles: list[str] = Field(default_factory=list)
    export_targets: list[str] = Field(default_factory=lambda: list(WORKFLOW_EXPORT_TARGETS))
    body: str = ""
    updated_at: str = ""

    @field_validator("workflow_id")
    @classmethod
    def valid_workflow_id(cls, value: str) -> str:
        if not WORKFLOW_ID_RE.fullmatch(value):
            raise ValueError("workflow_id must match [a-z0-9][a-z0-9._-]{0,79}")
        return value

    @field_validator("export_targets")
    @classmethod
    def unique_targets(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        for item in value:
            name = str(item).strip().lower()
            if name and name not in seen:
                seen.append(name)
        return seen

    @property
    def summary(self) -> str:
        return self.description.strip()[:240] or self.name


WorkflowAspect = Literal["16:9", "9:16", "4:5", "1:1", "auto"]

__all__ = [
    "WORKFLOW_EXPORT_TARGETS",
    "WORKFLOW_ID_RE",
    "WorkflowDefinition",
    "WorkflowStep",
]
