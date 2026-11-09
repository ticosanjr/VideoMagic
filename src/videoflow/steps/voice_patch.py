"""Voice repair: splice an approved clip or an optional TTS patch."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.tts import OpenAITtsAdapter
from videoflow.application.providers import first_provider
from videoflow.application.secrets import get_secret
from videoflow.core.context import PipelineContext
from videoflow.runtime import find_binary
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class VoicePatchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patch_path: str = Field(default="audio/voice-patch.wav", max_length=2000)
    start_sec: float = Field(default=0.0, ge=0.0, le=4 * 3600)
    end_sec: float = Field(default=0.0, ge=0.0, le=4 * 3600)
    text: str = Field(default="", max_length=8000)
    allow_tts: bool = True
    crossfade_ms: int = Field(default=0, ge=0, le=500)


@register_step
class VoicePatchStep(BaseStep):
    type = "voice.patch"
    title = "Repair voice"
    description = (
        "Replace a spoken segment with an approved clip or a configured TTS "
        "patch, then update the final dialogue master."
    )
    status = "available"
    icon = "◍"
    color = "#a78bfa"
    params_model = VoicePatchParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = VoicePatchParams.model_validate(params)
        answers = context.metadata.get("hilt_answers", {})
        answer_map = answers.get("answers", {}) if isinstance(answers, dict) else {}
        start = options.start_sec or float(answer_map.get("patch_start_sec") or 0.0)
        end = options.end_sec or float(answer_map.get("patch_end_sec") or 0.0)
        text = options.text or str(answer_map.get("voice_text") or "")
        master_value = context.artifacts.get("audio_mix") or context.artifacts.get(
            "audio_master"
        )
        master = Path(str(master_value)) if master_value else None
        if master is None or not master.is_file():
            context.warnings.append("Voice repair skipped: no final audio master.")
            io.report(100, "Voice repair skipped (no audio master)")
            return
        patch = Path(options.patch_path)
        if not patch.is_absolute():
            patch = context.output / patch
        if not patch.is_file() and options.allow_tts and text.strip():
            patch = self._tts_patch(context, text, io)
        if patch is None or not patch.is_file():
            context.warnings.append(
                "Voice repair skipped: no patch file or TTS provider."
            )
            io.report(100, "Voice repair skipped (no patch)")
            return
        duration = (
            context.media.duration_frames
            / max(0.001, context.media.fps_num / max(1, context.media.fps_den))
            if context.media is not None
            else start + 3.0
        )
        if end <= start:
            end = min(duration, start + 3.0)
        end = min(duration, end)
        if end <= start:
            context.warnings.append("Voice repair skipped: invalid segment.")
            io.report(100, "Voice repair skipped (invalid segment)")
            return
        binary = find_binary("ffmpeg")
        if binary is None:
            raise RuntimeError("FFmpeg is required for voice repair.")
        segment = max(0.05, end - start)
        target = context.output / "audio" / "final-repaired.wav"
        filters = []
        labels = []
        if start > 0:
            filters.append(
                f"[0:a]atrim=0:{start:.3f},asetpts=PTS-STARTPTS[pre]"
            )
            labels.append("[pre]")
        filters.append(
            f"[1:a]atrim=0:{segment:.3f},apad=whole_dur={segment:.3f},"
            f"atrim=0:{segment:.3f},asetpts=PTS-STARTPTS[patch]"
        )
        labels.append("[patch]")
        if end < duration:
            filters.append(
                f"[0:a]atrim={end:.3f},asetpts=PTS-STARTPTS[post]"
            )
            labels.append("[post]")
        filters.append(
            "".join(labels) + f"concat=n={len(labels)}:v=0:a=1[out]"
        )
        command = [
            binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(master),
            "-i",
            str(patch),
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[out]",
            "-c:a",
            "pcm_s16le",
            str(target),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(
                "Voice repair failed: " + (completed.stderr[-500:] or "unknown error")
            )
        shutil.copy2(target, context.output / "audio" / "master.wav")
        context.artifacts["audio_master"] = str(target)
        context.artifacts["audio_mix"] = str(target)
        context.artifacts["voice_patch"] = str(target)
        context.metadata["voice_patch"] = {
            "path": str(target),
            "patch": str(patch),
            "start_sec": start,
            "end_sec": end,
        }
        context.hashes["voice.patch"] = digest_payload(
            {"start": start, "end": end, "patch": str(patch)}
        )
        io.report(100, f"Voice patch applied at {start:.2f}s–{end:.2f}s")

    @staticmethod
    def _tts_patch(
        context: PipelineContext, text: str, io: StepIO
    ) -> Path | None:
        provider = first_provider("tts")
        if not provider:
            return None
        base_url = str(provider.get("base_url") or "")
        if not base_url:
            return None
        target = context.output / "audio" / "voice-patch-tts.mp3"
        try:
            OpenAITtsAdapter(
                base_url=base_url,
                model=str(provider.get("model") or "tts-1"),
                voice=str(provider.get("voice") or "alloy"),
                api_key=get_secret(
                    str(provider.get("api_key_env") or "VIDEOWFLOW_TTS_API_KEY")
                ),
            ).synthesize(text, target)
            io.emit("info", "Generated a TTS voice patch")
            return target
        except Exception as exc:  # noqa: BLE001 - file patch remains optional
            context.warnings.append(f"TTS voice patch fallback: {exc}")
            return None

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("voice_patch")
        return (Path(path),) if path else ()
