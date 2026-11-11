"""DeepSeek OpenAI-compatible provider defaults."""

from __future__ import annotations

from videoflow.application.intelligence.models import IntelligenceStatus
from videoflow.application.intelligence.providers.openai_compatible import (
    OpenAICompatibleProvider,
)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"


class DeepSeekProvider(OpenAICompatibleProvider):
    kind = "deepseek"

    def __init__(
        self,
        *,
        base_url: str = DEEPSEEK_BASE_URL,
        model: str = DEEPSEEK_MODEL,
        api_key: str = "",
        timeout: float = 120.0,
        retries: int = 2,
        temperature: float = 0.0,
        max_tokens: int = 0,
    ) -> None:
        super().__init__(
            provider_id="deepseek",
            base_url=base_url or DEEPSEEK_BASE_URL,
            model=model or DEEPSEEK_MODEL,
            api_key=api_key,
            timeout=timeout,
            retries=retries,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def status(self) -> IntelligenceStatus:
        ready = bool(self.base_url and self.model and self._api_key)
        return IntelligenceStatus(
            provider=self.id,
            kind=self.kind,
            ready=ready,
            detail="ready" if ready else "missing API key",
            models=[self.model] if self.model else [],
        )
