"""Human-in-the-loop interaction contract.

One interaction is persisted beside the project output. It is deliberately
plain JSON so an agent, the studio UI, an e-mail reply, or a chat message can
all resolve the same durable request.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

InteractionKind = Literal["approval", "question", "files", "review"]
InteractionStatus = Literal[
    "pending", "answered", "approved", "rejected", "expired", "cancelled"
]
QuestionType = Literal["text", "textarea", "choice", "boolean", "number", "file"]
ResponseAction = Literal["approve", "reject", "submit"]


class HiltModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HiltQuestion(HiltModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    label: str = Field(min_length=1, max_length=500)
    type: QuestionType = "text"
    required: bool = True
    options: list[Any] = Field(default_factory=list)
    default: Any = None
    placeholder: str = Field(default="", max_length=300)
    help: str = Field(default="", max_length=2000)
    accept: list[str] = Field(default_factory=list)
    max_mb: int = Field(default=512, ge=1, le=8192)

    @model_validator(mode="after")
    def choice_has_options(self) -> HiltQuestion:
        if self.type == "choice" and not self.options:
            raise ValueError("choice questions need at least one option")
        return self


class HiltFileRequest(HiltModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    label: str = Field(min_length=1, max_length=500)
    required: bool = True
    accept: list[str] = Field(default_factory=list)
    max_mb: int = Field(default=512, ge=1, le=8192)
    target: str = Field(default="", max_length=1000)
    allow_replace: bool = True
    help: str = Field(default="", max_length=2000)


class HiltArtifact(HiltModel):
    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=500)
    path: str = Field(min_length=1, max_length=4000)
    kind: str = Field(default="file", max_length=40)
    description: str = Field(default="", max_length=2000)
    exists: bool = False
    size_bytes: int = Field(default=0, ge=0)


class HiltRequest(HiltModel):
    schema_version: Literal[1] = 1
    interaction_id: str = Field(min_length=1, max_length=120)
    job_id: str = Field(default="", max_length=120)
    recipe_id: str = Field(default="", max_length=120)
    step_id: str = Field(default="", max_length=80)
    gate_id: str = Field(default="review", max_length=80)
    kind: InteractionKind = "approval"
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=8000)
    approve_label: str = Field(default="Approve", max_length=80)
    reject_label: str = Field(default="Reject", max_length=80)
    questions: list[HiltQuestion] = Field(default_factory=list)
    files: list[HiltFileRequest] = Field(default_factory=list)
    artifacts: list[HiltArtifact] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=lambda: ["local"])
    status: InteractionStatus = "pending"
    created_at: str = ""
    expires_at: str = ""
    reminder_at: str = ""
    token_required: bool = False
    token_hash: str = ""

    @model_validator(mode="after")
    def unique_ids(self) -> HiltRequest:
        for label, items in (
            ("question", [item.id for item in self.questions]),
            ("file", [item.id for item in self.files]),
            ("artifact", [item.id for item in self.artifacts]),
        ):
            if len(items) != len(set(items)):
                raise ValueError(f"duplicate {label} id")
        return self

    def public(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", exclude={"token_hash"})
        payload["response_url"] = (
            f"/api/v1/jobs/{self.job_id}/interactions/{self.interaction_id}/respond"
        )
        payload["files_url"] = (
            f"/api/v1/jobs/{self.job_id}/interactions/{self.interaction_id}/files"
        )
        return payload


class HiltAttachment(HiltModel):
    request_id: str = Field(default="", max_length=80)
    original_name: str = Field(min_length=1, max_length=500)
    stored_path: str = Field(min_length=1, max_length=1000)
    size_bytes: int = Field(default=0, ge=0)
    sha256: str = Field(default="", max_length=64)
    content_type: str = Field(default="", max_length=200)


class HiltResponse(HiltModel):
    schema_version: Literal[1] = 1
    interaction_id: str = Field(min_length=1, max_length=120)
    action: ResponseAction = "submit"
    answers: dict[str, Any] = Field(default_factory=dict)
    comment: str = Field(default="", max_length=8000)
    attachments: list[HiltAttachment] = Field(default_factory=list)
    responder: str = Field(default="local", max_length=200)
    response_channel: str = Field(default="local", max_length=40)
    received_at: str = ""
    resumed_job_id: str = Field(default="", max_length=120)

    def public(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class HiltEvent(HiltModel):
    at: str = ""
    event: str = Field(min_length=1, max_length=80)
    detail: dict[str, Any] = Field(default_factory=dict)
