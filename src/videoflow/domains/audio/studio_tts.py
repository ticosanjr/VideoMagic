"""Text-to-speech, voice cleanup and stem separation."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..toolkit import commands, storage
from ..toolkit.assets import (
    _assets_payload,
    _ensure_input,
    _ffmpeg,
    _materialize_remote,
    _path_from_value,
    _payload,
    _require_output,
    _slug,
)
from ..toolkit.errors import (
    InvalidArgumentError,
    MissingCommandError,
    OutputNotProducedError,
    RemoteResultError,
)
from . import studio_common
from .studio_common import AUDIO_EXTENSIONS, _audio_suffix, _output_name, _stem_name


def tts_generate(
    project_id: str,
    text: str,
    voice_ref_path: str | None = None,
    language: str = "pt",
    quality: str = "auto",
    output_name: str = "",
) -> dict[str, Any]:
    """Generate a voice-over with a local TTS command or a remote `tts` capability."""

    tool = "tts_generate"
    if not isinstance(text, str) or not text.strip():
        raise InvalidArgumentError("text must not be empty", details={"argument": "text"})
    if quality not in {"auto", "draft", "local", "final"}:
        raise InvalidArgumentError(
            "quality must be one of: auto, draft, local, final",
            details={"argument": "quality", "value": quality},
        )
    voice = _ensure_input(voice_ref_path, "voice_ref_path") if voice_ref_path else None
    key = storage.cache_key(tool, text, str(voice), language, quality)
    name = _output_name(output_name, f"tts_{_slug(text)}_{key[:8]}.wav")
    relative = f"assets/audio/{name}"

    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")

    if quality == "final" and studio_common.ROUTER.health("tts"):
        result = studio_common.ROUTER.submit(
            "tts",
            {
                "text": text,
                "voice_ref": str(voice) if voice else None,
                "language": language,
                "output_name": name,
            },
        )
        record = _materialize_remote(
            project_id=project_id,
            relative_path=relative,
            result=result,
            capability="tts",
            cache_key=key,
            kind="voice",
        )
        return _payload(tool, project_id, record, mode="remote")

    template = os.environ.get("VF_POCKET_TTS_CMD") or os.environ.get("VF_PIPER_CMD")
    if not template:
        raise MissingCommandError(
            "local TTS needs VF_POCKET_TTS_CMD or VF_PIPER_CMD, "
            "or a remote 'tts' capability for quality='final'",
            details={"env": ["VF_POCKET_TTS_CMD", "VF_PIPER_CMD"], "capability": "tts"},
        )

    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    values = {
        "text": text,
        "output": str(target),
        "voice": str(voice) if voice else "",
        "voice_ref": str(voice) if voice else "",
        "language": language,
    }
    commands.run(commands.expand_template(template, values, name="TTS command"))
    _require_output(target)
    backend = "piper" if os.environ.get("VF_PIPER_CMD") else "pocket-tts"
    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind="voice",
        license="generated",
        source=f"local:{backend}",
        cache_key=key,
        ai_generated=True,
        metadata={
            "language": language,
            "quality": quality,
            "voice_ref": str(voice) if voice else "",
        },
    )
    return _payload(tool, project_id, record, mode="local")


def voice_clean_and_enhance(
    project_id: str,
    input_audio_path: str,
    remove_reverb: bool = True,
) -> dict[str, Any]:
    """Clean a voice recording with FFmpeg and optional DeepFilterNet."""

    tool = "voice_clean_and_enhance"
    source = _ensure_input(input_audio_path, "input_audio_path")
    key = storage.cache_key(tool, storage.file_fingerprint(source), bool(remove_reverb))
    relative = f"assets/audio/{source.stem}_clean.wav"

    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")

    ffmpeg = _ffmpeg()
    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="vf-voice-clean-") as raw:
        workdir = Path(raw)
        prepared = source
        deepfilter = os.environ.get("VF_DEEPFILTER_CMD")
        if deepfilter:
            filtered = workdir / "deepfilter.wav"
            commands.run(
                commands.expand_template(
                    deepfilter,
                    {"input": str(source), "output": str(filtered)},
                    name="DeepFilterNet command",
                )
            )
            if not filtered.is_file():
                raise OutputNotProducedError(
                    "DeepFilterNet did not produce its output",
                    details={"path": str(filtered)},
                )
            prepared = filtered

        filter_chain = build_voice_clean_filter(remove_reverb=remove_reverb)
        commands.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(prepared),
                "-af",
                filter_chain,
                "-ar",
                "48000",
                "-c:a",
                "pcm_s16le",
                str(target),
            ]
        )

    _require_output(target)
    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind="voice",
        license="source",
        source="ffmpeg:voice-clean",
        cache_key=key,
        metadata={
            "remove_reverb": bool(remove_reverb),
            "deep_filter": bool(os.environ.get("VF_DEEPFILTER_CMD")),
            "filter": filter_chain,
        },
    )
    return _payload(tool, project_id, record, mode="local")


def separate_audio_stems(
    project_id: str,
    input_path: str,
    stems: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Separate a mix into stems with a remote `stems` capability or a local tool."""

    tool = "separate_audio_stems"
    source = _ensure_input(input_path, "input_path")
    wanted = [_stem_name(stem) for stem in (stems or ["vocals", "instrumental"])]
    if not wanted:
        raise InvalidArgumentError("stems must contain at least one stem name")

    if studio_common.ROUTER.health("stems"):
        result = studio_common.ROUTER.submit("stems", {"input": str(source), "stems": wanted})
        records = _remote_stem_records(project_id, result, wanted)
        return _assets_payload(tool, project_id, records, mode="remote")

    template = os.environ.get("VF_AUDIO_SEPARATOR_CMD")
    if not template:
        raise MissingCommandError(
            "stem separation needs VF_AUDIO_SEPARATOR_CMD or a remote 'stems' capability",
            details={"env": ["VF_AUDIO_SEPARATOR_CMD"], "capability": "stems"},
        )

    output_dir = storage.project_dir(project_id) / "assets" / "stems"
    output_dir.mkdir(parents=True, exist_ok=True)
    commands.run(
        commands.expand_template(
            template,
            {
                "input": str(source),
                "output": str(output_dir),
                "output_dir": str(output_dir),
                "stems": ",".join(wanted),
            },
            name="audio separator command",
        )
    )

    records = []
    for stem in wanted:
        matches = [
            path
            for path in sorted(output_dir.rglob(f"{stem}.*"))
            if path.suffix.lower() in AUDIO_EXTENSIONS
        ]
        if not matches:
            raise OutputNotProducedError(
                f"audio separator did not produce the {stem!r} stem",
                details={"stem": stem, "directory": str(output_dir)},
            )
        relative = f"assets/stems/{stem}{matches[0].suffix.lower()}"
        key = storage.cache_key(tool, storage.file_fingerprint(source), stem)
        records.append(
            storage.write_output(
                project_id,
                relative,
                source_path=matches[0],
                kind="voice",
                license="source",
                source="local:separator",
                cache_key=key,
                metadata={"stem": stem, "input": str(source)},
            )
        )
    return _assets_payload(tool, project_id, records, mode="local")


def build_voice_clean_filter(*, remove_reverb: bool = True) -> str:
    """FFmpeg chain used by `voice_clean_and_enhance`."""

    filters = ["highpass=f=80", "afftdn=nf=-25"]
    if remove_reverb:
        filters.append("deesser=i=0.4")
    filters.append("acompressor=threshold=0.125:ratio=3:attack=15:release=150:makeup=2")
    filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    return ",".join(filters)


def _remote_stem_records(
    project_id: str,
    result: Any,
    wanted: Sequence[str],
) -> list[storage.AssetRecord]:
    records: list[storage.AssetRecord] = []
    payload = result if isinstance(result, dict) else {}
    raw_stems = payload.get("stems") if isinstance(payload, dict) else None
    if isinstance(raw_stems, dict):
        for stem, value in raw_stems.items():
            safe = _stem_name(stem)
            source = _path_from_value(value)
            relative = f"assets/stems/{safe}{_audio_suffix(source)}"
            records.append(
                storage.write_output(
                    project_id,
                    relative,
                    source_path=source,
                    kind="voice",
                    license="source",
                    source="remote:stems",
                    cache_key=storage.cache_key("separate_audio_stems", stem, str(source)),
                    metadata={"stem": safe, "mode": "remote"},
                )
            )
        if records:
            return records

    source = _path_from_value(result)
    if source is None:
        raise RemoteResultError(
            "remote 'stems' capability returned no stem files",
            details={"capability": "stems", "stems": list(wanted)},
        )
    stem = wanted[0]
    relative = f"assets/stems/{stem}{_audio_suffix(source)}"
    records.append(
        storage.write_output(
            project_id,
            relative,
            source_path=source,
            kind="voice",
            license="source",
            source="remote:stems",
            cache_key=storage.cache_key("separate_audio_stems", stem, str(source)),
            metadata={"stem": stem, "mode": "remote"},
        )
    )
    return records
