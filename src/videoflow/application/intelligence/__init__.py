"""Unified intelligence layer: OpenCode V2, DeepSeek, and OpenAI-compatible."""

from videoflow.application.intelligence.models import (
    IntelligenceError,
    IntelligenceResult,
    IntelligenceStatus,
    ProviderResult,
)
from videoflow.application.intelligence.router import (
    Intelligence,
    IntelligenceLlmAdapter,
    build_intelligence,
    build_llm_adapter,
)
from videoflow.application.intelligence.tasks import (
    ScorePayload,
    score_prompt,
    validate_score,
)

__all__ = [
    "Intelligence",
    "IntelligenceError",
    "IntelligenceLlmAdapter",
    "IntelligenceResult",
    "IntelligenceStatus",
    "ProviderResult",
    "ScorePayload",
    "build_intelligence",
    "build_llm_adapter",
    "score_prompt",
    "validate_score",
]
