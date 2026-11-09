"""MCP Short editing, metadata, voice, dubbing, and analysis tools."""

from __future__ import annotations

import os
from typing import Any

from videoflow.application.caption_ai import apply_llm_emoji
from videoflow.application.dubbing import generate_short_dubbing
from videoflow.application.multimodal import analyze_short_entry
from videoflow.application.multimodal_llm import analyze_short_llm_entry
from videoflow.application.short_editor import ShortEditOptions
from videoflow.application.short_editor import edit_short as edit_short_service
from videoflow.application.short_metadata import generate_short_metadata
from videoflow.application.thumbnail import generate_short_thumbnail
from videoflow.application.voiceover import generate_short_voiceover
from videoflow.domain.config import DubbingConfig, TtsConfig
from videoflow.domain.errors import (
    CapabilityUnavailableError,
    StateNotReadyError,
    VideoFlowError,
)
from videoflow.domain.state import ProjectState
from videoflow.mcp_server.context import ToolContext, error


def register_short_tools(register: Any, ctx: ToolContext) -> None:
    """Register every Short post-production tool."""

    manager = ctx.manager
    last = ctx.last

    @register
    def videoflow_edit_short(
        index: int,
        title: str | None = None,
        start_sec: float | None = None,
        end_sec: float | None = None,
        aspect_ratio: str | None = None,
        burn_subtitles: bool | None = None,
        caption_style: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Trim, retitle, reframe, and re-render one Short from a completed job."""

        if index < 0:
            return error("invalid_arguments", "index must be non-negative")
        if aspect_ratio is not None and aspect_ratio not in {"9:16", "1:1", "16:9"}:
            return error(
                "invalid_arguments", "aspect_ratio must be 9:16, 1:1, or 16:9"
            )
        if start_sec is not None and end_sec is not None and end_sec <= start_sec:
            return error(
                "invalid_arguments", "end_sec must be greater than start_sec"
            )
        job_id = last.get("job_id")
        if not isinstance(job_id, str):
            return error("job_required", "Run a recipe with videoflow_run_recipe first.")
        try:
            job = manager.get(job_id)
            if job.status != "succeeded" or job.result is None:
                raise StateNotReadyError(
                    "The job must succeed before a Short can be edited."
                )
            entry = edit_short_service(
                source=job.source,
                output=job.output,
                index=index,
                result=job.result,
                options=ShortEditOptions(
                    title=title,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    aspect_ratio=aspect_ratio,
                    burn_subtitles=burn_subtitles,
                    caption_style=caption_style,
                ),
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "short": entry,
            "download": f"/api/v1/jobs/{job_id}/shorts/{index}",
        }

    @register
    def videoflow_generate_short_emoji(
        index: int,
        base_url: str | None = None,
        model: str = "qwen2.5:7b-instruct",
        allow_external_services: bool = False,
        allowed_external_hosts: list[str] | None = None,
    ) -> dict[str, object]:
        """Generate an LLM emoji map and re-render one Short captions."""

        job_id = last.get("job_id")
        if not isinstance(job_id, str):
            return error("job_required", "Run a recipe with videoflow_run_recipe first.")
        try:
            job = manager.get(job_id)
            if job.status != "succeeded" or job.result is None:
                raise StateNotReadyError(
                    "The job must succeed before captions can be edited."
                )
            payload = apply_llm_emoji(
                source=job.source,
                output=job.output,
                index=index,
                result=job.result,
                base_url=base_url
                or os.environ.get("VIDEOWFLOW_LLM_BASE_URL")
                or "http://localhost:11434/v1",
                model=model,
                api_key=os.environ.get("VIDEOWFLOW_LLM_API_KEY"),
                allow_external_services=allow_external_services,
                allowed_external_hosts=tuple(allowed_external_hosts or ()),
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "emoji_map": payload["emoji_map"],
            "short": payload["short"],
        }

    @register
    def videoflow_generate_short_metadata(
        index: int,
        platform: str = "youtube",
        tone: str = "engaging",
        extra_hashtags: list[str] | None = None,
    ) -> dict[str, object]:
        """Generate platform-aware title, description, and hashtags for a Short."""

        if platform not in {"youtube", "tiktok", "instagram", "linkedin"}:
            return error("invalid_arguments", "Unsupported platform")
        if tone not in {"engaging", "professional", "educational", "bold"}:
            return error("invalid_arguments", "Unsupported tone")
        job_id = last.get("job_id")
        if not isinstance(job_id, str):
            return error("job_required", "Run a recipe with videoflow_run_recipe first.")
        try:
            job = manager.get(job_id)
            if job.status != "succeeded" or job.result is None:
                raise StateNotReadyError(
                    "The job must succeed before metadata can be generated."
                )
            metadata = generate_short_metadata(
                output=job.output,
                index=index,
                result=job.result,
                platform=platform,
                tone=tone,
                extra_hashtags=tuple(extra_hashtags or ()),
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "metadata": metadata,
            "short": job.result["shorts"][index],
        }

    @register
    def videoflow_generate_short_thumbnail(
        index: int,
        time_sec: float | None = None,
        title: str | None = None,
        caption_style: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Extract one Short frame and burn a title-style thumbnail."""

        job_id = last.get("job_id")
        if not isinstance(job_id, str):
            return error("job_required", "Run a recipe with videoflow_run_recipe first.")
        try:
            job = manager.get(job_id)
            if job.status != "succeeded" or job.result is None:
                raise StateNotReadyError(
                    "The job must succeed before a thumbnail can be generated."
                )
            thumbnail = generate_short_thumbnail(
                output=job.output,
                index=index,
                result=job.result,
                time_sec=time_sec,
                title=title,
                caption_style=caption_style,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "thumbnail": thumbnail,
            "short": job.result["shorts"][index],
        }

    @register
    def videoflow_generate_short_voiceover(
        index: int,
        text: str,
        base_url: str | None = None,
        model: str = "tts-1",
        voice: str = "alloy",
        speed: float = 1.0,
        volume: float = 1.0,
        original_volume: float = 0.35,
        allow_external_services: bool = False,
        allowed_external_hosts: list[str] | None = None,
    ) -> dict[str, object]:
        """Generate TTS and mix a voice-over over a completed Short."""

        job_id = last.get("job_id")
        if not isinstance(job_id, str):
            return error("job_required", "Run a recipe with videoflow_run_recipe first.")
        try:
            job = manager.get(job_id)
            if job.status != "succeeded" or job.result is None:
                raise StateNotReadyError(
                    "The job must succeed before a voice-over can be generated."
                )
            state = ProjectState.model_validate_json(
                (job.output / "project_state.json").read_text(encoding="utf-8")
            )
            stored = state.modules_config.tts
            config = TtsConfig(
                provider="openai_compatible",
                base_url=base_url or stored.base_url,
                model=model or stored.model,
                voice=voice or stored.voice,
                secret_name=stored.secret_name,
                speed=speed,
                volume=volume,
                original_volume=original_volume,
            )
            payload = generate_short_voiceover(
                output=job.output,
                index=index,
                result=job.result,
                text=text,
                config=config,
                api_key=os.environ.get(config.secret_name),
                allow_external_services=allow_external_services,
                allowed_external_hosts=tuple(allowed_external_hosts or ()),
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "voiceover": payload,
            "short": job.result["shorts"][index],
        }

    @register
    def videoflow_dub_short(
        index: int,
        target_language: str = "en",
        text: str | None = None,
        base_url: str | None = None,
        model: str = "tts-1",
        voice: str = "alloy",
        speed: float = 1.0,
        volume: float = 1.0,
        original_volume: float = 0.0,
        llm_base_url: str | None = None,
        llm_model: str = "qwen2.5:7b-instruct",
        allow_external_services: bool = False,
        allowed_external_hosts: list[str] | None = None,
    ) -> dict[str, object]:
        """Translate and dub one completed Short with external TTS."""

        job_id = last.get("job_id")
        if not isinstance(job_id, str):
            return error("job_required", "Run a recipe with videoflow_run_recipe first.")
        try:
            job = manager.get(job_id)
            if job.status != "succeeded" or job.result is None:
                raise StateNotReadyError(
                    "The job must succeed before dubbing can be generated."
                )
            state = ProjectState.model_validate_json(
                (job.output / "project_state.json").read_text(encoding="utf-8")
            )
            stored_tts = state.modules_config.tts
            tts = TtsConfig(
                provider="openai_compatible",
                base_url=base_url or stored_tts.base_url,
                model=model or stored_tts.model,
                voice=voice or stored_tts.voice,
                secret_name=stored_tts.secret_name,
                speed=speed,
                volume=volume,
                original_volume=original_volume,
            )
            dubbing = DubbingConfig(
                target_language=target_language,
                original_volume=original_volume,
            )
            payload = generate_short_dubbing(
                output=job.output,
                index=index,
                result=job.result,
                source_text=text,
                target_language=target_language,
                tts=tts,
                dubbing=dubbing,
                llm_base_url=(
                    llm_base_url
                    or state.modules_config.retakes.base_url
                    or "http://localhost:11434/v1"
                ),
                llm_model=llm_model or state.modules_config.retakes.model_name,
                llm_api_key=os.environ.get("VIDEOWFLOW_LLM_API_KEY"),
                tts_api_key=os.environ.get(tts.secret_name),
                allow_external_services=allow_external_services,
                allowed_external_hosts=tuple(allowed_external_hosts or ()),
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "dubbing": payload,
            "short": job.result["shorts"][index],
        }

    @register
    def videoflow_analyze_short(index: int) -> dict[str, object]:
        """Run optional audio-emotion and visual-motion analysis on a Short."""

        job_id = last.get("job_id")
        if not isinstance(job_id, str):
            return error("job_required", "Run a recipe with videoflow_run_recipe first.")
        try:
            job = manager.get(job_id)
            if job.status != "succeeded" or job.result is None:
                raise StateNotReadyError("The job must succeed before analysis.")
            analysis = analyze_short_entry(
                output=job.output,
                index=index,
                result=job.result,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "analysis": analysis,
            "short": job.result["shorts"][index],
        }

    @register
    def videoflow_analyze_short_llm(
        index: int,
        base_url: str | None = None,
        model: str = "gpt-4o-mini",
        max_frames: int = 6,
        allow_external_services: bool = False,
        allowed_external_hosts: list[str] | None = None,
    ) -> dict[str, object]:
        """Analyze Short frames with an OpenAI-compatible vision model."""

        job_id = last.get("job_id")
        if not isinstance(job_id, str):
            return error("job_required", "Run a recipe with videoflow_run_recipe first.")
        try:
            job = manager.get(job_id)
            if job.status != "succeeded" or job.result is None:
                raise StateNotReadyError("The job must succeed before analysis.")
            endpoint = base_url or os.environ.get("VIDEOWFLOW_VISION_BASE_URL")
            if not endpoint:
                raise CapabilityUnavailableError(
                    "external_vision",
                    "Configure a vision endpoint or VIDEOWFLOW_VISION_BASE_URL.",
                )
            analysis = analyze_short_llm_entry(
                output=job.output,
                index=index,
                result=job.result,
                base_url=endpoint,
                model=model
                or os.environ.get("VIDEOWFLOW_VISION_MODEL", "gpt-4o-mini"),
                api_key=os.environ.get("VIDEOWFLOW_VISION_API_KEY"),
                allow_external_services=allow_external_services,
                allowed_external_hosts=tuple(allowed_external_hosts or ()),
                max_frames=max_frames,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {
            "ok": True,
            "analysis": analysis,
            "short": job.result["shorts"][index],
        }
