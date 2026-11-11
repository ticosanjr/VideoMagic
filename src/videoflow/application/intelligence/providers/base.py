"""Provider protocol for intelligence backends."""

from __future__ import annotations

from typing import Protocol

from videoflow.application.intelligence.models import IntelligenceStatus, ProviderResult


class TextProvider(Protocol):
    id: str
    kind: str

    def status(self) -> IntelligenceStatus: ...

    def complete_json(
        self,
        prompt: str,
        schema_name: str,
        *,
        model: str = "",
        timeout: float = 120.0,
        temperature: float = 0.0,
        max_tokens: int = 0,
    ) -> ProviderResult: ...

    def generate_image(
        self,
        prompt: str,
        *,
        model: str = "",
        width: int = 1024,
        height: int = 1024,
        count: int = 1,
        timeout: float = 120.0,
    ) -> list[bytes]: ...
