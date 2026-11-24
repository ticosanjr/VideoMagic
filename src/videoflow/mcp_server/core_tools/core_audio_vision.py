"""VideoFlow core MCP tools: audio, vision and fonts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.application.projects import get_project, load_project_state
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.context import error


def register(register: Any, ctx: Any, legacy: dict[str, Any]) -> None:
    @register
    def vf_audio(
        action: str = "tts",
        project_id: str = "",
        text: str = "",
        input_path: str = "",
        voice_ref_path: str = "",
        language: str = "pt",
        quality: str = "auto",
        remove_reverb: bool = True,
        stems: list[str] | None = None,
        prompt: str = "",
        duration_sec: float = 12.0,
        type: str = "music",
        music_path: str = "",
        target_lufs: float = -15.5,
        output_name: str = "",
    ) -> dict[str, Any]:
        """TTS, voice cleanup, stems, music/Foley, or a mastered mix."""

        from videoflow.domains.audio import studio

        try:
            if action == "tts":
                return studio.tts_generate(
                    project_id,
                    text,
                    voice_ref_path=voice_ref_path or None,
                    language=language,
                    quality=quality,
                    output_name=output_name,
                )
            if action == "clean":
                return studio.voice_clean_and_enhance(
                    project_id,
                    input_path,
                    remove_reverb=remove_reverb,
                )
            if action == "stems":
                return studio.separate_audio_stems(project_id, input_path, stems=stems)
            if action == "music":
                return studio.generate_music_or_sfx(
                    project_id,
                    prompt,
                    duration_sec,
                    type=type,
                )
            if action == "mix":
                return studio.mix_and_master_track(
                    project_id,
                    input_path,
                    music_path=music_path or None,
                    target_lufs=target_lufs,
                    output_name=output_name or "master.wav",
                )
            if action == "master":
                from videoflow.core.context import PipelineContext
                from videoflow.steps.audio_finalize import (
                    AudioFinalizeParams,
                    AudioFinalizeStep,
                )
                from videoflow.steps.base import StepIO

                record = get_project(project_id)
                state = load_project_state(record)
                output = Path(record.output).expanduser()
                source = (
                    Path(state.media_info.source_path).expanduser()
                    if state.media_info is not None
                    else Path(record.primary_source or record.output).expanduser()
                )
                context = PipelineContext(
                    source=source,
                    output=output,
                    work=output / "work",
                    exports=output / "exports",
                    media=state.media_info,
                    state=state,
                )
                AudioFinalizeStep().run(
                    context,
                    AudioFinalizeParams(
                        target_lufs=target_lufs,
                        target_name=output_name or "final.wav",
                    ),
                    StepIO(stage="audio.finalize"),
                )
                return {
                    "ok": True,
                    "project_id": record.project_id,
                    "audio_final": context.artifacts.get("audio_final", ""),
                    "audio_final_mix": context.artifacts.get("audio_final_mix", ""),
                    "audio_master": context.artifacts.get("audio_master", ""),
                    "finalize": context.metadata.get("audio_finalize", {}),
                }
            return error(
                "unknown_action",
                "vf_audio supports tts, clean, stems, music, mix, or master",
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except Exception as exc:  # noqa: BLE001 - keep MCP errors structured
            return error("audio_failed", str(exc))

    @register
    def vf_vision(
        action: str = "captions",
        project_id: str = "",
        input_path: str = "",
        audio_path: str = "",
        language: str = "pt",
        style: str = "shorts_karaoke",
        is_video: bool = False,
        scale: int = 2,
        backend: str = "auto",
    ) -> dict[str, Any]:
        """Word-aligned captions, background removal, or media upscale."""

        from videoflow.domains.vision.tools import (
            remove_background,
            transcribe_word_aligned,
            upscale_media,
        )

        try:
            if action == "captions":
                return transcribe_word_aligned(
                    project_id,
                    audio_path or input_path,
                    language=language,
                    style=style,
                )
            if action == "matte":
                return remove_background(project_id, input_path, is_video=is_video)
            if action == "upscale":
                return upscale_media(
                    project_id,
                    input_path,
                    scale=scale,
                    backend=backend,
                )
            return error(
                "unknown_action",
                "vf_vision supports captions, matte, or upscale",
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except Exception as exc:  # noqa: BLE001 - keep MCP errors structured
            return error("vision_failed", str(exc))

    @register
    def vf_font(
        action: str = "list",
        family: str = "",
        font_path: str = "",
        name: str = "",
    ) -> dict[str, Any]:
        """List or resolve real fonts, including virtual metric aliases."""

        from videoflow.application.fonts import (
            font_aliases,
            fontconfig_fonts,
            list_fonts,
            list_system_fonts,
            register_font,
            resolve_font_family,
        )

        try:
            if action == "list":
                requested = str(family or "").strip()
                resolved = resolve_font_family(requested) if requested else None
                return {
                    "ok": True,
                    "fonts": list_fonts(),
                    "system": list_system_fonts(),
                    "fontconfig": fontconfig_fonts(),
                    "aliases": font_aliases(),
                    "family": requested,
                    "resolved": resolved or requested,
                }
            if action == "resolve":
                return {
                    "ok": True,
                    "family": family,
                    "resolved": resolve_font_family(family),
                    "aliases": font_aliases(),
                }
            if action == "register":
                if not font_path:
                    return error("font_required", "font_path is required")
                return {"ok": True, "font": register_font(Path(font_path), name=name)}
            return error("unknown_action", "vf_font supports list, resolve, or register")
        except VideoFlowError as exc:
            return exc.to_dict()
        except Exception as exc:  # noqa: BLE001 - keep MCP errors structured
            return error("font_failed", str(exc))

    @register
    def vf_preview(
        project_id: str,
        mode: str = "caption",
        time_sec: float = 0.0,
        platform: str = "youtube_16_9",
    ) -> dict[str, Any]:
        """Render a caption or overlay preview with ordered frames."""

        try:
            record = get_project(project_id)
            state = load_project_state(record)
            output = Path(record.output)
            if mode == "caption":
                from videoflow.application.caption_preview import (
                    render_caption_preview,
                )

                result = render_caption_preview(state, output, time_sec=time_sec)
            elif mode == "overlay":
                from videoflow.application.overlay_preview import (
                    render_overlay_preview,
                )

                result = render_overlay_preview(
                    state, output, time_sec=time_sec, platform=platform
                )
            else:
                return error("unknown_mode", "vf_preview supports caption or overlay")
            return {"ok": True, "project_id": project_id, "mode": mode, "preview": result}
        except VideoFlowError as exc:
            return exc.to_dict()
        except (OSError, ValueError) as exc:
            return error("preview_failed", str(exc))
