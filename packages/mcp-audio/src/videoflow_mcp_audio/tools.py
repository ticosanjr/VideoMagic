"""VideoFlow 2.90 audio tools: TTS, cleanup, stems, music/SFX, and mastering."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from . import commands, storage
from .errors import (
    InputNotFoundError,
    InvalidArgumentError,
    MissingCommandError,
    OutputNotProducedError,
    RemoteResultError,
)
from .router import RouterBridge

ROUTER = RouterBridge()
AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus"}


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

    if quality == "final" and ROUTER.health("tts"):
        result = ROUTER.submit(
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

    if ROUTER.health("stems"):
        result = ROUTER.submit("stems", {"input": str(source), "stems": wanted})
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


def generate_music_or_sfx(
    project_id: str,
    prompt: str,
    duration_sec: float,
    type: str = "music",
) -> dict[str, Any]:
    """Generate a deterministic local bed or use a remote `music`/`sfx` capability."""

    tool = "generate_music_or_sfx"
    kind = (type or "").strip().lower()
    if kind not in {"music", "sfx"}:
        raise InvalidArgumentError(
            "type must be 'music' or 'sfx'",
            details={"argument": "type", "value": type},
        )
    if not isinstance(prompt, str) or not prompt.strip():
        raise InvalidArgumentError("prompt must not be empty", details={"argument": "prompt"})
    try:
        duration = float(duration_sec)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError(
            "duration_sec must be a number",
            details={"argument": "duration_sec", "value": duration_sec},
        ) from exc
    if not 0.25 <= duration <= 600.0:
        raise InvalidArgumentError(
            "duration_sec must be between 0.25 and 600",
            details={"argument": "duration_sec", "value": duration_sec},
        )

    key = storage.cache_key(tool, prompt, duration, kind)
    relative = f"assets/audio/{kind}_{_slug(prompt)}_{key[:8]}.wav"
    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")

    if ROUTER.health(kind):
        result = ROUTER.submit(
            kind,
            {"prompt": prompt, "duration_sec": duration, "type": kind},
        )
        record = _materialize_remote(
            project_id=project_id,
            relative_path=relative,
            result=result,
            capability=kind,
            cache_key=key,
            kind=kind,
        )
        return _payload(tool, project_id, record, mode="remote")

    ffmpeg = _ffmpeg()
    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="vf-bed-") as raw:
        workdir = Path(raw)
        if kind == "music":
            bed = workdir / "bed.wav"
            _write_music_bed(bed, duration, prompt)
            commands.run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(bed),
                    "-af",
                    "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-ar",
                    "48000",
                    "-c:a",
                    "pcm_s16le",
                    str(target),
                ]
            )
            source_name = "procedural:numpy+ffmpeg"
        else:
            fade_out = max(0.05, duration - 0.35)
            filter_chain = (
                "highpass=f=200,lowpass=f=6000,"
                f"afade=t=in:st=0:d=0.15,afade=t=out:st={fade_out:.3f}:d=0.35,"
                "volume=0.8"
            )
            commands.run(
                [
                    ffmpeg,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"anoisesrc=color=pink:duration={duration:.3f}:amplitude=0.35",
                    "-af",
                    filter_chain,
                    "-ar",
                    "48000",
                    "-c:a",
                    "pcm_s16le",
                    str(target),
                ]
            )
            source_name = "procedural:ffmpeg"

    _require_output(target)
    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind=kind,
        license="generated",
        source=source_name,
        cache_key=key,
        ai_generated=True,
        metadata={"prompt": prompt, "duration_sec": duration, "type": kind},
    )
    return _payload(tool, project_id, record, mode="local")


def mix_and_master_track(
    project_id: str,
    voice_path: str,
    music_path: str | None = None,
    sfx_events: Sequence[dict[str, Any]] | None = None,
    target_lufs: float = -14.0,
    output_name: str = "master.wav",
) -> dict[str, Any]:
    """Duck music under the voice, place SFX, and master with loudnorm."""

    tool = "mix_and_master_track"
    voice = _ensure_input(voice_path, "voice_path")
    music = _ensure_input(music_path, "music_path") if music_path else None
    events = _normalize_sfx_events(sfx_events or [])
    try:
        lufs = float(target_lufs)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError(
            "target_lufs must be a number",
            details={"argument": "target_lufs", "value": target_lufs},
        ) from exc
    if not -60.0 <= lufs <= 0.0:
        raise InvalidArgumentError(
            "target_lufs must be between -60 and 0",
            details={"argument": "target_lufs", "value": target_lufs},
        )

    name = _output_name(output_name, "master.wav")
    if not name.lower().endswith(".wav"):
        name = f"{Path(name).stem}.wav"
    relative = f"assets/audio/{name}"

    key = storage.cache_key(
        tool,
        storage.file_fingerprint(voice),
        storage.file_fingerprint(music) if music else "",
        [
            (
                storage.file_fingerprint(event["path"]),
                event["start"],
                event["gain_db"],
            )
            for event in events
        ],
        lufs,
    )
    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")

    ffmpeg = _ffmpeg()
    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)

    argv = [ffmpeg, "-y", "-i", str(voice)]
    if music:
        argv.extend(["-i", str(music)])
    for event in events:
        argv.extend(["-i", event["path"]])

    graph = build_mix_graph(
        has_music=music is not None,
        sfx_count=len(events),
        target_lufs=lufs,
        sfx_starts=[event["start"] for event in events],
        sfx_gains=[event["gain_db"] for event in events],
    )
    argv.extend(
        [
            "-filter_complex",
            graph,
            "-map",
            "[out]",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s16le",
            str(target),
        ]
    )
    commands.run(argv)
    _require_output(target)

    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind="voice",
        license="generated",
        source="ffmpeg:mix",
        cache_key=key,
        metadata={
            "voice": str(voice),
            "music": str(music) if music else "",
            "sfx_events": len(events),
            "target_lufs": lufs,
            "ducking": music is not None,
        },
    )
    return _payload(
        tool,
        project_id,
        record,
        mode="local",
        ducking=music is not None,
        sfx_count=len(events),
    )


def build_voice_clean_filter(*, remove_reverb: bool = True) -> str:
    """FFmpeg chain used by `voice_clean_and_enhance`."""

    filters = ["highpass=f=80", "afftdn=nf=-25"]
    if remove_reverb:
        filters.append("deesser=i=0.4")
    filters.append("acompressor=threshold=0.125:ratio=3:attack=15:release=150:makeup=2")
    filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    return ",".join(filters)


def build_mix_graph(
    *,
    has_music: bool,
    sfx_count: int,
    target_lufs: float = -14.0,
    sfx_starts: Sequence[float] | None = None,
    sfx_gains: Sequence[float] | None = None,
) -> str:
    """Build the filter_complex graph for sidechain ducking and mastering."""

    starts = list(sfx_starts or [0.0] * sfx_count)
    gains = list(sfx_gains or [0.0] * sfx_count)
    if len(starts) != sfx_count or len(gains) != sfx_count:
        raise InvalidArgumentError("sfx timing lists must match sfx_count")

    lines: list[str] = []
    mix_inputs: list[str] = []
    if has_music:
        lines.append("[0:a]asplit=2[voice][key]")
        lines.append("[1:a]volume=0.9[music]")
        lines.append(
            "[music][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[ducked]"
        )
        mix_inputs.extend(["[voice]", "[ducked]"])
    else:
        mix_inputs.append("[0:a]")

    first_sfx_index = 2 if has_music else 1
    for index in range(sfx_count):
        delay = max(0, int(round(float(starts[index]) * 1000)))
        gain = float(gains[index])
        gain_filter = f",volume={gain:g}dB" if gain else ""
        lines.append(
            f"[{first_sfx_index + index}:a]adelay={delay}|{delay}{gain_filter}[sfx{index}]"
        )
        mix_inputs.append(f"[sfx{index}]")

    loudnorm = f"loudnorm=I={float(target_lufs):.1f}:TP=-1.0:LRA=11"
    if len(mix_inputs) == 1:
        lines.append(f"{mix_inputs[0]}{loudnorm}[out]")
    else:
        lines.append(
            "".join(mix_inputs)
            + f"amix=inputs={len(mix_inputs)}:normalize=0:duration=longest[mixed]"
        )
        lines.append(f"[mixed]{loudnorm}[out]")
    return ";\n".join(lines)


def _write_music_bed(path: Path, duration: float, prompt: str, sample_rate: int = 48000) -> None:
    """Render a deterministic stereo pad/bass bed with numpy."""

    seed = int(hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    frames = max(1, int(round(duration * sample_rate)))
    timeline = np.arange(frames, dtype=np.float64) / sample_rate

    scale = (0.0, 2.0, 3.0, 5.0, 7.0, 8.0, 10.0)
    root = 110.0 * (2.0 ** ((seed % 5) / 12.0))
    signal = np.zeros(frames, dtype=np.float64)

    chord_length = max(0.5, duration / 4.0)
    for start in np.arange(0.0, duration, chord_length):
        begin = int(start * sample_rate)
        end = min(frames, int((start + chord_length) * sample_rate))
        if end <= begin:
            continue
        local = timeline[begin:end] - start
        envelope = np.sin(np.pi * local / chord_length) ** 2
        for degree in (0, 3, 4, 5):
            frequency = root * 2.0 ** (scale[degree] / 12.0)
            signal[begin:end] += envelope * np.sin(2.0 * np.pi * frequency * local)
        signal[begin:end] += 0.5 * envelope * np.sin(np.pi * root * local)

    for start in np.arange(0.0, duration, 0.5):
        begin = int(start * sample_rate)
        end = min(frames, int((start + 0.15) * sample_rate))
        if end <= begin:
            continue
        local = timeline[begin:end] - start
        signal[begin:end] += 0.35 * np.exp(-local * 18.0) * np.sin(2.0 * np.pi * 60.0 * local)

    signal += 0.01 * rng.standard_normal(frames)
    peak = float(np.max(np.abs(signal))) or 1.0
    signal = signal / peak * 0.30
    stereo = np.stack([signal, np.roll(signal, 240)], axis=1)
    pcm = (np.clip(stereo, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def _normalize_sfx_events(events: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise InvalidArgumentError(
                f"sfx_events[{index}] must be an object",
                details={"argument": "sfx_events", "index": index},
            )
        raw_path = event.get("path") or event.get("file")
        resolved = _ensure_input(raw_path, f"sfx_events[{index}].path")
        try:
            start = float(event.get("start", 0.0))
            gain = float(event.get("gain_db", 0.0))
        except (TypeError, ValueError) as exc:
            raise InvalidArgumentError(
                f"sfx_events[{index}] start and gain_db must be numbers",
                details={"argument": "sfx_events", "index": index},
            ) from exc
        if start < 0:
            raise InvalidArgumentError(
                f"sfx_events[{index}].start must be >= 0",
                details={"argument": "sfx_events", "index": index},
            )
        normalized.append({"path": str(resolved), "start": start, "gain_db": gain})
    return normalized


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


def _materialize_remote(
    *,
    project_id: str,
    relative_path: str,
    result: Any,
    capability: str,
    cache_key: str,
    kind: str,
) -> storage.AssetRecord:
    metadata: dict[str, Any] = {"capability": capability, "mode": "remote"}
    if isinstance(result, dict) and isinstance(result.get("metadata"), dict):
        metadata.update(result["metadata"])

    data: bytes | None = None
    if isinstance(result, dict) and result.get("data") is not None:
        raw = result["data"]
        data = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
    elif isinstance(result, (bytes, bytearray)):
        data = bytes(result)

    if data is not None:
        return storage.write_output(
            project_id,
            relative_path,
            data=data,
            kind=kind,
            license="generated",
            source=f"remote:{capability}",
            cache_key=cache_key,
            metadata=metadata,
            ai_generated=True,
        )

    source = _path_from_value(result)
    if source is None or not source.is_file():
        raise RemoteResultError(
            f"remote {capability!r} result has no readable file",
            details={"capability": capability, "result_type": type(result).__name__},
        )
    return storage.write_output(
        project_id,
        relative_path,
        source_path=source,
        kind=kind,
        license="generated",
        source=f"remote:{capability}",
        cache_key=cache_key,
        metadata=metadata,
        ai_generated=True,
    )


def _path_from_value(value: Any) -> Path | None:
    if isinstance(value, (str, Path)):
        return Path(str(value)).expanduser()
    if isinstance(value, dict):
        for key in ("path", "output", "asset_path", "file"):
            if value.get(key):
                return Path(str(value[key])).expanduser()
        return None
    for attribute in ("path", "output", "file"):
        raw = getattr(value, attribute, None)
        if raw:
            return Path(str(raw)).expanduser()
    return None


def _payload(
    tool: str,
    project_id: str,
    record: storage.AssetRecord,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "tool": tool,
        "project_id": project_id,
        "output": str(record.path),
        "relative_path": record.relative_path,
        "cache_key": record.cache_key,
        "cached": record.cached,
        "sidecar": str(record.sidecar),
        "license": record.license,
        "source": record.source,
        "sha256": record.sha256,
    }
    payload.update(extra)
    return payload


def _assets_payload(
    tool: str,
    project_id: str,
    records: Sequence[storage.AssetRecord],
    *,
    mode: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "tool": tool,
        "project_id": project_id,
        "mode": mode,
        "cached": all(record.cached for record in records),
        "assets": [_payload(tool, project_id, record, mode=mode) for record in records],
    }


def _ensure_input(value: str | Path | None, argument: str) -> Path:
    if value is None or str(value) == "":
        raise InvalidArgumentError(f"{argument} is required", details={"argument": argument})
    resolved = Path(value).expanduser()
    if not resolved.is_file():
        raise InputNotFoundError(
            f"{argument} not found: {resolved}",
            details={"argument": argument, "path": str(resolved)},
        )
    return resolved


def _require_output(path: Path) -> None:
    if not path.is_file():
        raise OutputNotProducedError(
            f"command did not produce {path}",
            details={"path": str(path)},
        )


def _output_name(value: str, default: str) -> str:
    raw = value.strip() if value else default
    name = Path(raw).name
    if name in {"", ".", ".."}:
        raise InvalidArgumentError(f"invalid output name: {value!r}")
    return name


def _slug(value: str, *, limit: int = 40) -> str:
    cleaned = "".join(character if character.isalnum() else "_" for character in value.lower())
    collapsed = "_".join(part for part in cleaned.split("_") if part)
    return (collapsed or "asset")[:limit]


def _stem_name(value: str) -> str:
    raw = str(value).strip().lower()
    cleaned = "".join(
        character if character.isalnum() or character in {"_", "-"} else "_" for character in raw
    )
    if not cleaned or cleaned in {".", ".."}:
        raise InvalidArgumentError(
            f"invalid stem name: {value!r}",
            details={"argument": "stems", "value": value},
        )
    return cleaned


def _audio_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    return suffix if suffix in AUDIO_EXTENSIONS else ".wav"


def _ffmpeg() -> str:
    configured = os.environ.get("VF_FFMPEG")
    if configured:
        return configured
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise MissingCommandError(
        "ffmpeg is required for this tool; install it or set VF_FFMPEG",
        details={"env": ["VF_FFMPEG"], "executable": "ffmpeg"},
    )
