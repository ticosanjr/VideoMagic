"""Recipe step for per-Short localization and dubbing."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.dubbing import generate_short_dubbing
from videoflow.application.providers import first_provider
from videoflow.application.secrets import get_secret
from videoflow.application.settings import load_settings
from videoflow.core.context import PipelineContext
from videoflow.domain.config import DubbingConfig, TtsConfig
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class DubbingParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_language: str = Field(default="en", min_length=2, max_length=20)
    base_url: str | None = None
    model: str = ""
    voice: str = ""
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    volume: float = Field(default=1.0, ge=0.0, le=1.0)
    original_volume: float = Field(default=0.0, ge=0.0, le=1.0)
    llm_base_url: str | None = None
    llm_model: str = ""
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)


@register_step
class DubbingStep(BaseStep):
    type = "localization.dub"
    title = "Localize and dub"
    description = "Translate and synthesize a dubbed Short for each rendered clip."
    status = "available"
    icon = "◍"
    color = "#22c55e"
    requires = ("shorts.render",)
    produces = ("dubbed_shorts",)
    params_model = DubbingParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = DubbingParams.model_validate(params)
        settings = load_settings()
        provider = first_provider("tts") or {}
        base_url = options.base_url or str(provider.get("base_url") or "")
        if not base_url:
            io.report(100, "Dubbing skipped: no TTS provider configured")
            return
        tts = TtsConfig(
            provider="openai_compatible",
            base_url=base_url,
            model=options.model or settings.tts.model or str(provider.get("model") or "tts-1"),
            voice=options.voice or settings.tts.voice or "alloy",
            secret_name=str(provider.get("api_key_env") or "VIDEOWFLOW_TTS_API_KEY"),
            speed=options.speed,
            volume=options.volume,
            original_volume=options.original_volume,
        )
        llm_provider = first_provider("llm") or {}
        result = {"ok": True, "shorts": list(context.shorts)}
        dubbed = []
        for index, _ in enumerate(context.shorts):
            try:
                payload = generate_short_dubbing(
                    output=context.output,
                    index=index,
                    result=result,
                    source_text=None,
                    target_language=options.target_language,
                    tts=tts,
                    dubbing=DubbingConfig(
                        target_language=options.target_language,
                        original_volume=options.original_volume,
                    ),
                    llm_base_url=(
                        options.llm_base_url
                        or str(llm_provider.get("base_url") or "")
                        or "http://localhost:11434/v1"
                    ),
                    llm_model=(
                        options.llm_model
                        or str(llm_provider.get("model") or "")
                        or "qwen2.5:7b-instruct"
                    ),
                    llm_api_key=get_secret("VIDEOWFLOW_LLM_API_KEY"),
                    tts_api_key=get_secret(tts.secret_name),
                    allow_external_services=options.allow_external_services,
                    allowed_external_hosts=tuple(options.allowed_external_hosts),
                )
                dubbed.append(payload)
            except Exception as exc:
                context.warnings.append(f"Dubbing failed for Short {index}: {exc}")
            io.report(int((index + 1) / max(1, len(context.shorts)) * 100), f"Dubbed {index + 1}")
        context.metadata["dubbed_shorts"] = dubbed
        context.artifacts["dubbed_shorts"] = str(
            context.output / "localization" / "dubbed.json"
        )
        path = Path(context.artifacts["dubbed_shorts"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dubbed, indent=2) + "\n", encoding="utf-8")
        io.report(100, f"{len(dubbed)} dubbed Short(s)")
