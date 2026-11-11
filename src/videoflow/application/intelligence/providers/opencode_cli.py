"""OpenCode CLI provider adapter."""

from __future__ import annotations

import time

from videoflow.adapters.opencode import OpenCodeLlm
from videoflow.application.intelligence.models import (
    IntelligenceStatus,
    ProviderResult,
)
from videoflow.domain.errors import LlmError


class OpenCodeCliProvider:
    kind = "opencode_cli"

    def __init__(
        self,
        *,
        binary: str = "opencode",
        model: str = "default",
        timeout: float = 120.0,
    ) -> None:
        self.id = "opencode_cli"
        self.binary = binary
        self.model = model
        self.timeout = timeout

    def status(self) -> IntelligenceStatus:
        return IntelligenceStatus(
            provider=self.id,
            kind=self.kind,
            ready=bool(self.binary),
            detail="CLI bridge; starts one process per call",
            models=[self.model],
        )

    def complete_json(
        self,
        prompt: str,
        schema_name: str,
        *,
        model: str = "",
        timeout: float = 120.0,
        temperature: float = 0.0,
        max_tokens: int = 0,
    ) -> ProviderResult:
        selected = model or self.model
        started = time.perf_counter()
        try:
            data = OpenCodeLlm(
                binary=self.binary,
                model=selected,
                timeout=timeout or self.timeout,
            ).complete_json(prompt, schema_name)
        except LlmError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize provider failures
            raise LlmError(f"OpenCode CLI failed: {exc}") from exc
        return ProviderResult(
            data=data,
            provider=self.id,
            model=selected,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )

    def generate_image(
        self,
        prompt: str,
        *,
        model: str = "",
        width: int = 1024,
        height: int = 1024,
        count: int = 1,
        timeout: float = 120.0,
    ) -> list[bytes]:
        raise LlmError("OpenCode CLI does not expose image generation")
