"""Core intelligence models shared by providers and the router."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderResult:
    data: dict[str, Any]
    provider: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


@dataclass
class IntelligenceResult:
    data: dict[str, Any]
    task: str
    provider: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    fallback: str = "none"
    errors: list[str] = field(default_factory=list)


@dataclass
class IntelligenceStatus:
    provider: str
    kind: str
    ready: bool
    detail: str = ""
    models: list[str] = field(default_factory=list)


class IntelligenceError(Exception):
    """Raised when no provider can satisfy a task."""

    def __init__(self, message: str, *, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []
