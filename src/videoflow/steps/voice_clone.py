"""Generate a voice-clone repair clip for the fact-check patch step."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application import voice_clone
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import VideoFlowError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class VoiceCloneParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(default="", max_length=120)
    text: str = Field(default="", max_length=8000)
    output_path: str = Field(default="audio/voice-patch.mp3", max_length=2000)


@register_step
class VoiceCloneStep(BaseStep):
    type = "voice.clone"
    title = "Clone voice repair"
    description = (
        "Synthesize the fact-check repair line with an approved voice-clone "
        "profile. The resulting clip is consumed by voice.patch."
    )
    status = "available"
    icon = "◍"
    color = "#a78bfa"
    params_model = VoiceCloneParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = VoiceCloneParams.model_validate(params)
        answers = context.metadata.get("hilt_answers", {})
        answer_map = answers.get("answers", {}) if isinstance(answers, dict) else {}
        profile_id = options.profile_id or str(answer_map.get("voice_profile_id") or "").strip()
        text = options.text or str(answer_map.get("voice_text") or "").strip()
        human_patch = context.output / "audio" / "voice-patch.wav"
        if human_patch.is_file():
            io.report(100, "Human voice patch present; clone skipped")
            return
        if not profile_id or not text:
            context.warnings.append(
                "Voice clone skipped: no profile id or repair text was supplied."
            )
            io.report(100, "Voice clone skipped (no profile/text)")
            return
        try:
            audio = voice_clone.synthesize(
                voice_clone.VoiceSynthesizeRequest(
                    profile_id=profile_id,
                    text=text,
                )
            )
        except VideoFlowError as exc:
            context.warnings.append(f"Voice clone unavailable: {exc.message}")
            io.emit("warning", f"Voice clone unavailable: {exc.message}", module="voice.clone")
            io.report(100, "Voice clone unavailable; patch/TTS fallback remains")
            return
        target = context.output / options.output_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(audio)
        context.artifacts["voice_clone_patch"] = str(target)
        context.metadata["voice_clone_patch"] = {
            "profile_id": profile_id,
            "path": str(target),
            "bytes": len(audio),
        }
        context.hashes["voice.clone"] = digest_payload(
            {"profile_id": profile_id, "bytes": len(audio)}
        )
        io.report(100, "Voice clone repair clip generated")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("voice_clone_patch")
        return (Path(path),) if path else ()
