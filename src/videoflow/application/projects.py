"""Project registry, atomic state revisions, and project run options."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from uuid import UUID

from videoflow.application.presets import get_preset
from videoflow.application.storage import atomic_write_text, utc_now
from videoflow.domain.config import JlCutsConfig, ModuleEnabled, ZoomsConfig
from videoflow.domain.errors import (
    InvalidOverrideError,
    ProjectNotFoundError,
    ProjectStateError,
    UnknownModuleError,
    WordOverridesNotSupportedError,
)
from videoflow.domain.paths import resolve_allowed
from videoflow.domain.state import ManualOverride, MediaInfo, Preset, ProjectState
from videoflow.runtime import allowed_roots

REGISTRY_VERSION = 1


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    project_id: UUID
    root: Path
    revision: int
    created_at: str
    updated_at: str

    @property
    def videoflow_dir(self) -> Path:
        return self.root / ".videoflow"

    @property
    def state_path(self) -> Path:
        return self.videoflow_dir / "project_state.json"

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": str(self.project_id),
            "root": str(self.root),
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ProjectStore:
    """Persist projects under ``<root>/.videoflow`` and index them by id."""

    def __init__(self, home: Path | None = None) -> None:
        self._home = Path(home) if home is not None else None
        self._lock = threading.RLock()

    def create(
        self, root: Path, *, preset: str | None = None
    ) -> tuple[ProjectRecord, ProjectState]:
        with self._lock:
            resolved = resolve_allowed(Path(root), allowed_roots())
            if resolved.exists() and not resolved.is_dir():
                raise ProjectStateError(f"Project root is not a directory: {resolved}")
            resolved.mkdir(parents=True, exist_ok=True)
            videoflow = resolved / ".videoflow"
            videoflow.mkdir(parents=True, exist_ok=True)
            (videoflow / "revisions").mkdir(parents=True, exist_ok=True)
            (videoflow / "work").mkdir(parents=True, exist_ok=True)
            state_path = videoflow / "project_state.json"
            now = utc_now()
            if state_path.is_file():
                state = self._read_state_path(state_path)
                existing = self._find_optional(state.project_id)
                created = existing.created_at if existing is not None else now
                record = ProjectRecord(
                    project_id=state.project_id,
                    root=resolved,
                    revision=state.revision,
                    created_at=created,
                    updated_at=now,
                )
                self._ensure_snapshot(record, state)
                self._upsert(record)
                if preset is not None:
                    state, record = self.save_state(
                        state.project_id, apply_preset(state, get_preset(preset).preset)
                    )
                return record, state

            state = ProjectState()
            if preset is not None:
                state = apply_preset(state, get_preset(preset).preset)
            state = state.model_copy(update={"revision": 1})
            record = ProjectRecord(
                project_id=state.project_id,
                root=resolved,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            self._write_state_files(record, state)
            self._upsert(record)
            return record, state

    def get(self, project_id: UUID | str) -> ProjectRecord:
        try:
            identifier = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        except ValueError as exc:
            raise ProjectNotFoundError(project_id) from exc
        record = self._find_optional(identifier)
        if record is None:
            raise ProjectNotFoundError(identifier)
        resolve_allowed(record.root, allowed_roots())
        return record

    def list(self) -> tuple[ProjectRecord, ...]:
        return tuple(sorted(self._read_registry(), key=lambda item: item.updated_at, reverse=True))

    def read_state(self, project_id: UUID | str) -> ProjectState:
        record = self.get(project_id)
        return self._read_state(record)

    def save_state(
        self, project_id: UUID | str, state: ProjectState
    ) -> tuple[ProjectState, ProjectRecord]:
        with self._lock:
            record = self.get(project_id)
            current = self._read_state(record)
            revision = max(record.revision, current.revision) + 1
            updated = state.model_copy(update={"revision": revision})
            self._write_state_files(record, updated)
            updated_record = replace(record, revision=revision, updated_at=utc_now())
            self._upsert(updated_record)
            return updated, updated_record

    def record_job_state(self, project_id: UUID | str) -> ProjectState:
        """Snapshot the state written by a successful pipeline job."""

        with self._lock:
            record = self.get(project_id)
            state = self._read_state(record)
            self._ensure_snapshot(record, state)
            updated_record = replace(
                record,
                revision=max(record.revision, state.revision),
                updated_at=utc_now(),
            )
            self._upsert(updated_record)
            return state

    def run_options(self, record: ProjectRecord, state: ProjectState) -> dict[str, Any]:
        config = state.modules_config
        enabled = state.module_enabled
        jl = config.jl_cuts
        if not enabled.jl_cuts:
            jl = JlCutsConfig(
                enable_j_cuts=False,
                enable_l_cuts=False,
                offset_ms=config.jl_cuts.offset_ms,
                audio_crossfade_ms=config.jl_cuts.audio_crossfade_ms,
                handle_check=config.jl_cuts.handle_check,
            )
        zooms = config.zooms
        if not enabled.zooms:
            zooms = ZoomsConfig(
                mode="manual_rules",
                punch_in_scale=config.zooms.punch_in_scale,
                anchor_point=config.zooms.anchor_point,
                progressive_zoom=False,
                pan_direction="none",
            )
        targets: list[str] = []
        if enabled.export:
            if config.export.write_fcpxml:
                targets.append("resolve")
            if config.export.write_xmeml:
                targets.append("premiere")
            if config.export.write_otio:
                targets.append("kdenlive")
        has_transcript = bool(state.transcript)
        return {
            "project_id": str(state.project_id),
            "revision": state.revision + 1,
            "modules_config": config.model_dump(mode="json"),
            "module_enabled": enabled.model_dump(mode="json"),
            "noise_db": -30.0,
            "min_silence_ms": config.vad.min_silence_duration_ms,
            "min_speech_ms": 100,
            "vad_engine": config.vad.engine,
            "speech_threshold": config.vad.speech_threshold,
            "speech_pad_before_ms": config.vad.speech_pad_before_ms,
            "speech_pad_after_ms": config.vad.speech_pad_after_ms,
            "jcut": jl.enable_j_cuts,
            "lcut": jl.enable_l_cuts,
            "offset_ms": jl.offset_ms,
            "crossfade_ms": jl.audio_crossfade_ms,
            "fade_in_ms": jl.fade_in_ms,
            "fade_out_ms": jl.fade_out_ms,
            "fade_curve": jl.fade_curve,
            "handle_check": jl.handle_check,
            "zooms": enabled.zooms,
            "zoom_mode": zooms.mode,
            "zoom_min_scale": zooms.min_scale,
            "zoom_max_scale": zooms.max_scale,
            "punch_in_scale": zooms.punch_in_scale,
            "anchor_point": zooms.anchor_point,
            "progressive_zoom": zooms.progressive_zoom,
            "pan_direction": zooms.pan_direction,
            "dialect": config.export.fcpxml_dialect,
            "export_targets": targets,
            "transcript_state": str(record.state_path) if has_transcript else None,
            "cull_retakes": enabled.retakes and has_transcript,
            "strictness": config.retakes.strictness,
            "retake_strategy": config.retakes.retake_strategy,
            "context_window": config.retakes.context_window_sentences,
            "llm_model": config.retakes.model_name,
            "shorts": enabled.shorts,
            "shorts_count": config.shorts.max_clips_to_generate,
            "shorts_min_count": config.shorts.min_clips,
            "shorts_min_sec": config.shorts.target_duration_min_sec,
            "shorts_max_sec": config.shorts.target_duration_max_sec,
            "shorts_subtitles": config.shorts.burn_subtitles,
            "shorts_selection_mode": config.shorts.selection_mode,
            "shorts_prompt": config.shorts.prompt,
            "shorts_reprompt": config.shorts.reprompt,
            "shorts_prompt_mode": config.shorts.prompt_mode,
            "shorts_hook_mode": config.shorts.hook_mode,
            "shorts_remove_fillers": config.shorts.remove_fillers,
            "shorts_filler_words": config.shorts.filler_words,
            "shorts_audio_energy_boost": config.shorts.audio_energy_boost,
            "shorts_scene_change_boost": config.shorts.scene_change_boost,
            "shorts_reframe_mode": config.shorts.reframe_mode,
            "shorts_aspect": config.shorts.aspect_ratio,
            "shorts_source_start_sec": config.shorts.source_start_sec,
            "shorts_source_end_sec": config.shorts.source_end_sec,
            "allow_external_services": config.providers.allow_external_services,
            "allowed_external_hosts": list(config.providers.allowed_hosts),
            "audio_enhance": config.audio.enabled,
            "audio_highpass_hz": config.audio.highpass_hz,
            "audio_denoise": config.audio.denoise,
            "audio_denoise_db": config.audio.denoise_db,
            "audio_noise_floor_db": config.audio.noise_floor_db,
            "audio_loudnorm": config.audio.loudnorm,
            "audio_target_lufs": config.audio.target_lufs,
            "audio_true_peak_db": config.audio.true_peak_db,
            "overlay_enabled": config.overlay.enabled,
            "overlay_asset": config.overlay.asset,
            "overlay_position": config.overlay.position,
            "overlay_margin_px": config.overlay.margin_px,
            "overlay_width_ratio": config.overlay.width_ratio,
            "overlay_opacity": config.overlay.opacity,
            "music_enabled": config.music.enabled,
            "music_asset": config.music.asset,
            "music_volume": config.music.volume,
            "music_ducking": config.music.ducking,
            "music_fade_in_ms": config.music.fade_in_ms,
            "music_fade_out_ms": config.music.fade_out_ms,
            "intro_enabled": config.intro_outro.intro_enabled,
            "intro_asset": config.intro_outro.intro_asset,
            "intro_duration_sec": config.intro_outro.intro_duration_sec,
            "outro_enabled": config.intro_outro.outro_enabled,
            "outro_asset": config.intro_outro.outro_asset,
            "outro_duration_sec": config.intro_outro.outro_duration_sec,
            "caption_font_family": config.shorts.caption_style.font_family,
            "caption_font_size": config.shorts.caption_style.font_size,
            "caption_font_weight": config.shorts.caption_style.font_weight,
            "caption_italic": config.shorts.caption_style.italic,
            "caption_uppercase": config.shorts.caption_style.uppercase,
            "caption_primary_color": config.shorts.caption_style.primary_color,
            "caption_highlight_color": config.shorts.caption_style.highlight_color,
            "caption_outline_color": config.shorts.caption_style.outline_color,
            "caption_outline_width": config.shorts.caption_style.outline_width,
            "caption_shadow_color": config.shorts.caption_style.shadow_color,
            "caption_shadow_offset": config.shorts.caption_style.shadow_offset,
            "caption_shadow_opacity": config.shorts.caption_style.shadow_opacity,
            "caption_background_color": config.shorts.caption_style.background_color,
            "caption_background_opacity": config.shorts.caption_style.background_opacity,
            "caption_background_padding": config.shorts.caption_style.background_padding,
            "caption_alignment": config.shorts.caption_style.alignment,
            "caption_position_x": config.shorts.caption_style.position_x,
            "caption_position_y": config.shorts.caption_style.position_y,
            "caption_max_width": config.shorts.caption_style.max_width,
            "caption_animation": config.shorts.caption_style.animation,
            "caption_word_timing": config.shorts.caption_style.word_timing,
            "caption_censor_enabled": config.shorts.caption_style.censor_enabled,
            "caption_censor_words": config.shorts.caption_style.censor_words,
            "caption_censor_replacement": config.shorts.caption_style.censor_replacement,
            "caption_keyword_highlight_enabled": (
                config.shorts.caption_style.keyword_highlight_enabled
            ),
            "caption_keyword_color": config.shorts.caption_style.keyword_color,
            "caption_keyword_words": config.shorts.caption_style.keyword_words,
            "caption_emoji_enabled": config.shorts.caption_style.emoji_enabled,
            "caption_emoji_map": config.shorts.caption_style.emoji_map,
            "caption_brand_vocabulary": config.shorts.caption_style.brand_vocabulary,
            "overrides": [item.model_dump(mode="json") for item in state.manual_overrides],
            "transcribe": enabled.transcribe and not has_transcript,
            "asr_language": config.transcribe.language,
            "whisper_engine": config.transcribe.engine,
            "whisper_model_size": config.transcribe.model_size,
            "whisper_device": config.transcribe.device,
            "whisper_compute_type": config.transcribe.compute_type,
            "whisper_vad_filter": config.transcribe.vad_filter,
        }

    def _home_dir(self) -> Path:
        if self._home is not None:
            return self._home
        from videoflow.runtime import ensure_home

        return ensure_home()

    def _registry_path(self) -> Path:
        return self._home_dir() / "projects.json"

    def _read_registry(self) -> list[ProjectRecord]:
        path = self._registry_path()
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectStateError(f"Cannot read the project registry: {exc}") from exc
        if not isinstance(payload, dict):
            raise ProjectStateError("The project registry must be a JSON object.")
        entries = payload.get("projects", [])
        if not isinstance(entries, list):
            raise ProjectStateError("The project registry projects field must be a list.")
        records: list[ProjectRecord] = []
        for entry in entries:
            try:
                records.append(
                    ProjectRecord(
                        project_id=UUID(str(entry["project_id"])),
                        root=Path(str(entry["root"])),
                        revision=max(1, int(entry.get("revision", 1))),
                        created_at=str(entry["created_at"]),
                        updated_at=str(entry["updated_at"]),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ProjectStateError(f"Invalid project registry entry: {exc}") from exc
        return records

    def _write_registry(self, records: list[ProjectRecord]) -> None:
        payload = {
            "schema_version": REGISTRY_VERSION,
            "projects": [
                {
                    "project_id": str(record.project_id),
                    "root": str(record.root),
                    "revision": record.revision,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                }
                for record in records
            ],
        }
        atomic_write_text(
            self._registry_path(),
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        )

    def _upsert(self, record: ProjectRecord) -> None:
        with self._lock:
            records = self._read_registry()
            records = [
                item
                for item in records
                if item.project_id != record.project_id and item.root != record.root
            ]
            records.append(record)
            self._write_registry(records)

    def _find_optional(self, project_id: UUID) -> ProjectRecord | None:
        for record in self._read_registry():
            if record.project_id == project_id:
                return record
        return None

    def _read_state(self, record: ProjectRecord) -> ProjectState:
        return self._read_state_path(record.state_path, project_id=record.project_id)

    def _read_state_path(
        self, path: Path, *, project_id: UUID | None = None
    ) -> ProjectState:
        try:
            state = ProjectState.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ProjectStateError(f"Cannot read project state {path}: {exc}") from exc
        if project_id is not None and state.project_id != project_id:
            raise ProjectStateError("Project state id does not match the registry entry.")
        return state

    def _write_state_files(self, record: ProjectRecord, state: ProjectState) -> None:
        body = state.model_dump_json(indent=2) + "\n"
        snapshot = record.videoflow_dir / "revisions" / f"{state.revision:06d}.json"
        atomic_write_text(snapshot, body)
        atomic_write_text(record.state_path, body)

    def _ensure_snapshot(self, record: ProjectRecord, state: ProjectState) -> None:
        snapshot = record.videoflow_dir / "revisions" / f"{state.revision:06d}.json"
        if snapshot.is_file():
            return
        atomic_write_text(snapshot, state.model_dump_json(indent=2) + "\n")


def apply_preset(state: ProjectState, preset: Preset) -> ProjectState:
    return state.model_copy(
        update={
            "modules_config": preset.modules_config,
            "module_enabled": preset.module_enabled,
        }
    )


def apply_media(state: ProjectState, media: MediaInfo) -> ProjectState:
    """Replace the source and invalidate every result derived from the old one."""

    return ProjectState.model_validate(
        {
            **state.model_dump(mode="json"),
            "media_info": media.model_dump(mode="json"),
            "cache_hashes": {},
            "vad_intervals": [],
            "transcript": [],
            "retake_culls": [],
            "retake_guard_restores": [],
            "manual_overrides": [],
            "video_segments": [],
            "audio_segments": [],
            "vertical_clips": [],
        }
    )


def apply_module_config(
    state: ProjectState, module_id: str, patch: dict[str, Any]
) -> ProjectState:
    current = getattr(state.modules_config, module_id, None)
    if current is None:
        raise UnknownModuleError(module_id)
    merged = {**current.model_dump(mode="json"), **patch}
    validated = type(current).model_validate(merged)
    configs = state.modules_config.model_dump(mode="json")
    configs[module_id] = validated.model_dump(mode="json")
    return ProjectState.model_validate(
        {
            **state.model_dump(mode="json"),
            "modules_config": configs,
            "cache_hashes": {},
        }
    )


def apply_module_enabled(
    state: ProjectState, module_id: str, enabled: bool
) -> ProjectState:
    if module_id not in ModuleEnabled.model_fields:
        raise UnknownModuleError(module_id)
    flags = state.module_enabled.model_dump(mode="json")
    flags[module_id] = enabled
    return ProjectState.model_validate(
        {
            **state.model_dump(mode="json"),
            "module_enabled": flags,
            "cache_hashes": {},
        }
    )


def apply_overrides(
    state: ProjectState, overrides: list[ManualOverride]
) -> ProjectState:
    """Replace overrides atomically and invalidate retakes plus downstream state."""

    valid = {sentence.id: sentence for sentence in state.transcript}
    for override in overrides:
        if override.sentence_id not in valid:
            raise InvalidOverrideError(
                f"Sentence id {override.sentence_id} is not in the transcript."
            )
        if override.word_index is not None:
            raise WordOverridesNotSupportedError(
                "Word-level retake culling is not supported; use a sentence override."
            )
    return ProjectState.model_validate(
        {
            **state.model_dump(mode="json"),
            "manual_overrides": [item.model_dump(mode="json") for item in overrides],
            "retake_culls": [],
            "retake_guard_restores": [],
            "video_segments": [],
            "audio_segments": [],
            "vertical_clips": [],
            "cache_hashes": {},
        }
    )
