"""Unified VideoFlow CLI. This is the single entry point used by the portable build."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import signal
import subprocess
import sys
import time
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path

from videoflow import __version__
from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.audio import audio_filters
from videoflow.application.fonts import fonts_dir
from videoflow.application.portable import run_portable
from videoflow.application.retakes import cull_intervals
from videoflow.application.retakes import cull_retakes as cull_transcript_retakes
from videoflow.application.shorts import (
    build_ass,
    previous_shorts_from_report,
    select_shorts,
    sentence_events,
    short_dimensions,
    slugify,
)
from videoflow.application.video_analysis import detect_scene_changes, scene_intervals
from videoflow.domain.config import (
    AudioEnhanceConfig,
    CaptionStyle,
    JlCutsConfig,
    ShortsConfig,
    TranscribeConfig,
    ZoomsConfig,
)
from videoflow.domain.errors import VideoFlowError
from videoflow.domain.timebase import Rounding
from videoflow.domain.transcript import parse_srt_file
from videoflow.exporters.common import write_text
from videoflow.runtime import (
    ensure_home,
    find_binary,
    find_faster_whisper_model,
    find_silero_model,
    find_whisper_binary,
    find_whisper_model,
    portable_home,
    ui_dir,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "version":
            return _version()
        if args.command == "doctor":
            return _doctor()
        if args.command == "run":
            return _run(args)
        if args.command == "demo":
            return _demo(args)
        if args.command == "shorts":
            return _shorts(args)
        if args.command == "serve":
            return _serve(args)
        if args.command == "stop":
            return _stop(args)
        if args.command == "restart":
            return _restart(args)
        if args.command == "status":
            return _status()
        if args.command == "mcp":
            return _mcp()
    except VideoFlowError as exc:
        print(json.dumps(exc.to_dict(), indent=2), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    parser.print_help()
    return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="videoflow",
        description="Local, portable video pre-edit pipeline.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("version", help="Print the version and exit.")
    sub.add_parser("doctor", help="Check FFmpeg, data directory, UI, and MCP.")

    run = sub.add_parser("run", help="Ingest, cut silence, and export three timelines.")
    run.add_argument("source", type=Path, help="Source video file.")
    run.add_argument("-o", "--out", type=Path, default=None, help="Project directory.")
    run.add_argument("--noise-db", type=float, default=-30.0, help="Silence threshold.")
    run.add_argument("--min-silence-ms", type=int, default=400, help="Shortest silence to cut.")
    run.add_argument(
        "--min-speech-ms",
        type=int,
        default=100,
        help="Ignore speech blips shorter than this (default 100).",
    )
    run.add_argument(
        "--vad-engine",
        choices=("auto", "silero", "ffmpeg"),
        default="auto",
        help="Speech detector: Silero when bundled, FFmpeg fallback, or force one.",
    )
    run.add_argument(
        "--speech-threshold",
        type=float,
        default=0.5,
        help="Silero speech probability threshold (0.1-0.9).",
    )
    run.add_argument(
        "--speech-pad-before-ms",
        type=int,
        default=120,
        help="Keep this much audio before detected speech (default 120).",
    )
    run.add_argument(
        "--speech-pad-after-ms",
        type=int,
        default=150,
        help="Keep this much audio after detected speech (default 150).",
    )
    run.add_argument("--no-jcuts", action="store_true", help="Disable J-cuts.")
    run.add_argument("--l-cuts", action="store_true", help="Enable L-cuts.")
    run.add_argument("--no-zooms", action="store_true", help="Disable punch-ins.")
    run.add_argument("--offset-ms", type=int, default=200)
    run.add_argument("--crossfade-ms", type=int, default=20)
    run.add_argument("--fade-in-ms", type=int, default=20)
    run.add_argument("--fade-out-ms", type=int, default=20)
    run.add_argument("--fade-curve", choices=("linear", "logarithmic"), default="logarithmic")
    run.add_argument("--zoom-min-scale", type=float, default=1.0)
    run.add_argument("--zoom-max-scale", type=float, default=1.5)
    run.add_argument("--dialect", choices=("1.9", "1.10"), default="1.9")
    run.add_argument("--transcript", type=Path, default=None, help="SRT subtitle file.")
    run.add_argument(
        "--transcribe",
        action="store_true",
        help="Transcribe with local Faster-Whisper or whisper.cpp, or an ASR URL.",
    )
    run.add_argument(
        "--whisper-engine",
        choices=("auto", "faster-whisper", "whisper.cpp"),
        default="auto",
        help="Local engine: Faster-Whisper when available, whisper.cpp fallback, or force one.",
    )
    run.add_argument(
        "--model-size",
        choices=("tiny", "base", "small", "medium", "large-v3"),
        default="small",
        help="Faster-Whisper model size (default small).",
    )
    run.add_argument(
        "--device",
        choices=("cpu", "cuda"),
        default="cpu",
        help="Faster-Whisper device (default cpu).",
    )
    run.add_argument(
        "--compute-type",
        choices=("int8", "float16", "float32"),
        default="int8",
        help="Faster-Whisper compute type (default int8).",
    )
    run.add_argument(
        "--whisper-vad",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable Faster-Whisper's own VAD filter; keep it off when module 02 runs.",
    )
    run.add_argument(
        "--asr-base-url",
        default=os.environ.get("VIDEOWFLOW_ASR_BASE_URL"),
        help="ASR base URL. Empty runs a local Faster-Whisper or whisper.cpp engine.",
    )
    run.add_argument(
        "--asr-model",
        default=os.environ.get("VIDEOWFLOW_ASR_MODEL", "whisper-1"),
    )
    run.add_argument(
        "--asr-language",
        choices=("pt", "it", "en", "es", "auto"),
        default="pt",
    )
    run.add_argument(
        "--faster-whisper-model",
        type=Path,
        default=None,
        help="Local CTranslate2 model directory; empty uses the selected bundled model.",
    )
    run.add_argument(
        "--whisper-model",
        type=Path,
        default=None,
        help="Local GGML model for whisper.cpp; empty uses the bundled ggml-tiny.bin.",
    )
    run.add_argument(
        "--shorts",
        action="store_true",
        help="Also render vertical Shorts alongside the main project.",
    )
    run.add_argument("--shorts-count", type=int, default=3)
    run.add_argument("--shorts-min-count", type=int, default=3)
    run.add_argument("--shorts-min-sec", type=int, default=30)
    run.add_argument("--shorts-max-sec", type=int, default=60)
    run.add_argument(
        "--shorts-aspect",
        choices=("9:16", "1:1", "16:9"),
        default="9:16",
        help="Short render aspect ratio.",
    )
    run.add_argument("--shorts-start-sec", type=float, default=0.0)
    run.add_argument(
        "--shorts-end-sec",
        type=float,
        default=None,
        help="End of the source window for Short selection; empty means the end.",
    )
    run.add_argument(
        "--shorts-selection-mode",
        choices=("auto", "llm", "heuristic"),
        default="auto",
    )
    run.add_argument(
        "--shorts-prompt",
        default="",
        help="Topic or instruction used to focus Short selection.",
    )
    run.add_argument(
        "--shorts-reprompt",
        default="",
        help="Refinement instruction for an existing Short selection.",
    )
    run.add_argument(
        "--shorts-prompt-mode",
        choices=("replace", "refine"),
        default="replace",
    )
    run.add_argument(
        "--shorts-hook-mode",
        choices=("off", "metadata", "repeat", "reorder"),
        default="off",
        help="Auto-hook behavior: metadata only, repeat at start, or reorder first.",
    )
    run.add_argument("--shorts-remove-fillers", action="store_true")
    run.add_argument("--shorts-audio-energy", action="store_true")
    run.add_argument("--shorts-scene-change", action="store_true")
    run.add_argument(
        "--shorts-reframe",
        choices=("center_crop_9_16", "motion_tracking", "face_tracking"),
        default="center_crop_9_16",
    )
    run.add_argument("--shorts-filler-word", action="append", default=[])
    run.add_argument("--caption-censor", action="store_true")
    run.add_argument("--caption-censor-word", action="append", default=[])
    run.add_argument("--caption-censor-replacement", default="***")
    run.add_argument("--audio-enhance", action="store_true")
    run.add_argument(
        "--no-shorts-subtitles",
        action="store_true",
        help="Disable burned captions in Shorts.",
    )
    run.add_argument(
        "--cull-retakes",
        action="store_true",
        help="Cull failed takes using the transcript (exact repeats without an LLM).",
    )
    run.add_argument(
        "--llm-base-url",
        default=os.environ.get("VIDEOWFLOW_LLM_BASE_URL"),
        help="OpenAI-compatible base URL. Defaults to VIDEOWFLOW_LLM_BASE_URL.",
    )
    run.add_argument(
        "--llm-model",
        default=os.environ.get("VIDEOWFLOW_LLM_MODEL", "qwen2.5:7b-instruct"),
    )
    run.add_argument(
        "--strictness",
        choices=("conservative", "balanced", "aggressive"),
        default="balanced",
    )
    run.add_argument(
        "--retake-strategy",
        choices=("keep_last", "keep_best"),
        default="keep_last",
    )
    run.add_argument("--context-window", type=int, default=15)

    demo = sub.add_parser("demo", help="Generate a fixture and run the full pipeline.")
    demo.add_argument("-o", "--out", type=Path, default=Path("videoflow-demo"))

    shorts = sub.add_parser("shorts", help="Select and render vertical 9:16 clips.")
    shorts.add_argument("source", type=Path)
    shorts.add_argument("-o", "--out", type=Path, default=None)
    shorts.add_argument("--transcript", type=Path, required=True, help="SRT transcript.")
    shorts.add_argument("--count", type=int, default=3)
    shorts.add_argument("--min-sec", type=int, default=30)
    shorts.add_argument("--max-sec", type=int, default=60)
    shorts.add_argument(
        "--aspect",
        choices=("9:16", "1:1", "16:9"),
        default="9:16",
        help="Render aspect ratio.",
    )
    shorts.add_argument("--start-sec", type=float, default=0.0)
    shorts.add_argument("--end-sec", type=float, default=None)
    shorts.add_argument("--prompt", default="", help="Topic or instruction for selection.")
    shorts.add_argument("--reprompt", default="", help="Refinement instruction.")
    shorts.add_argument("--prompt-mode", choices=("replace", "refine"), default="replace")
    shorts.add_argument(
        "--hook-mode",
        choices=("off", "metadata", "repeat", "reorder"),
        default="off",
    )
    shorts.add_argument("--remove-fillers", action="store_true")
    shorts.add_argument("--audio-energy", action="store_true")
    shorts.add_argument("--scene-change", action="store_true")
    shorts.add_argument(
        "--reframe",
        choices=("center_crop_9_16", "motion_tracking", "face_tracking"),
        default="center_crop_9_16",
    )
    shorts.add_argument("--filler-word", action="append", default=[])
    shorts.add_argument("--audio-enhance", action="store_true")
    shorts.add_argument("--no-subtitles", action="store_true")
    shorts.add_argument("--cull-retakes", action="store_true")
    shorts.add_argument("--llm-base-url", default=os.environ.get("VIDEOWFLOW_LLM_BASE_URL"))
    shorts.add_argument(
        "--llm-model",
        default=os.environ.get("VIDEOWFLOW_LLM_MODEL", "qwen2.5:7b-instruct"),
    )

    serve = sub.add_parser("serve", help="Serve the API, MCP HTTP, and rack UI.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument(
        "--open",
        action="store_true",
        help="Open the rack UI in the default browser after startup.",
    )

    stop = sub.add_parser("stop", help="Stop the local VideoFlow service.")
    stop.add_argument("--timeout", type=float, default=5.0)
    restart = sub.add_parser("restart", help="Restart the local service and keep it running.")
    restart.add_argument("--host", default="127.0.0.1")
    restart.add_argument("--port", type=int, default=8765)
    sub.add_parser("status", help="Show whether the local service is running.")
    sub.add_parser("mcp", help="Run the MCP server over stdio.")
    return parser


def _version() -> int:
    print(f"videoflow {__version__} ({platform.system().lower()}-{platform.machine()})")
    return 0


def _doctor() -> int:
    ensure_home()
    checks: dict[str, object] = {"version": __version__, "home": str(portable_home())}
    ok = True
    for name in ("ffmpeg", "ffprobe"):
        path = find_binary(name)
        entry: dict[str, object] = {"path": path, "found": path is not None}
        if path:
            completed = subprocess.run(
                [path, "-version"], capture_output=True, text=True, check=False
            )
            first = completed.stdout.splitlines()[0] if completed.stdout else ""
            entry["version"] = first
            entry["exit_code"] = completed.returncode
            ok = ok and completed.returncode == 0
        else:
            ok = False
        checks[name] = entry
    try:
        probe = portable_home() / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks["home_writable"] = True
    except OSError as exc:
        checks["home_writable"] = False
        checks["home_error"] = str(exc)
        ok = False
    checks["ui"] = str(ui_dir()) if ui_dir() else None
    whisper_binary = find_whisper_binary()
    whisper_model = find_whisper_model()
    checks["whisper"] = {
        "binary": whisper_binary,
        "model": str(whisper_model) if whisper_model else None,
        "found": bool(whisper_binary and whisper_model),
    }
    faster_whisper_model = find_faster_whisper_model("small")
    try:
        import faster_whisper

        faster_whisper_version: str | None = faster_whisper.__version__
    except Exception:  # pragma: no cover - optional runtime
        faster_whisper_version = None
    checks["faster_whisper"] = {
        "package": faster_whisper_version,
        "model": str(faster_whisper_model) if faster_whisper_model else None,
        "found": bool(faster_whisper_version and faster_whisper_model),
    }
    silero_model = find_silero_model()
    try:
        import onnxruntime

        onnxruntime_version: str | None = onnxruntime.__version__
    except Exception:  # pragma: no cover - optional runtime
        onnxruntime_version = None
    checks["silero"] = {
        "model": str(silero_model) if silero_model else None,
        "onnxruntime": onnxruntime_version,
        "found": bool(silero_model and onnxruntime_version),
    }
    try:
        import mcp  # noqa: F401

        checks["mcp"] = True
    except Exception as exc:  # pragma: no cover - packaging issue
        checks["mcp"] = False
        checks["mcp_error"] = str(exc)
        ok = False
    checks["ok"] = ok
    print(json.dumps(checks, indent=2))
    return 0 if ok else 1


def _run(args: argparse.Namespace) -> int:
    output = args.out or args.source.with_name(f"{args.source.stem}-videoflow")
    jl = JlCutsConfig(
        enable_j_cuts=not args.no_jcuts,
        enable_l_cuts=args.l_cuts,
        offset_ms=args.offset_ms,
        audio_crossfade_ms=args.crossfade_ms,
        fade_in_ms=args.fade_in_ms,
        fade_out_ms=args.fade_out_ms,
        fade_curve=args.fade_curve,
    )
    zooms = ZoomsConfig(
        mode="manual_rules" if args.no_zooms else "alternate_cuts",
        min_scale=args.zoom_min_scale,
        max_scale=args.zoom_max_scale,
    )
    if args.shorts_count < args.shorts_min_count:
        print("--shorts-count must be at least --shorts-min-count.", file=sys.stderr)
        return 2
    if args.shorts_end_sec is not None and args.shorts_end_sec <= args.shorts_start_sec:
        print("--shorts-end-sec must be greater than --shorts-start-sec.", file=sys.stderr)
        return 2
    shorts_config = ShortsConfig(
        target_duration_min_sec=args.shorts_min_sec,
        target_duration_max_sec=args.shorts_max_sec,
        min_clips=args.shorts_min_count,
        max_clips_to_generate=args.shorts_count,
        selection_mode=args.shorts_selection_mode,
        prompt=args.shorts_prompt,
        reprompt=args.shorts_reprompt,
        prompt_mode=args.shorts_prompt_mode,
        hook_mode=args.shorts_hook_mode,
        remove_fillers=args.shorts_remove_fillers,
        audio_energy_boost=args.shorts_audio_energy,
        scene_change_boost=args.shorts_scene_change,
        reframe_mode=args.shorts_reframe,
        filler_words=args.shorts_filler_word or ["hum", "hmm", "uh", "um", "ah", "eh", "erm", "er"],
        caption_style=CaptionStyle(
            censor_enabled=args.caption_censor,
            censor_words=args.caption_censor_word
            or ["porra", "merda", "caralho", "foda", "fuck", "shit", "bitch", "asshole"],
            censor_replacement=args.caption_censor_replacement,
        ),
        aspect_ratio=args.shorts_aspect,
        source_start_sec=args.shorts_start_sec,
        source_end_sec=args.shorts_end_sec,
        burn_subtitles=not args.no_shorts_subtitles,
    )
    if args.cull_retakes and args.transcript is None:
        print("--cull-retakes requires --transcript.", file=sys.stderr)
        return 2
    if not 0.1 <= args.speech_threshold <= 0.9:
        print("--speech-threshold must be between 0.1 and 0.9.", file=sys.stderr)
        return 2
    if args.speech_pad_before_ms < 0 or args.speech_pad_after_ms < 0:
        print("Speech pads must not be negative.", file=sys.stderr)
        return 2
    client = None
    if args.llm_base_url and (args.transcript is not None or args.transcribe or args.shorts):
        from videoflow.adapters.llm import OpenAICompatibleLlm

        client = OpenAICompatibleLlm(
            base_url=args.llm_base_url,
            model=args.llm_model,
            api_key=os.environ.get("VIDEOWFLOW_LLM_API_KEY"),
        )
    result = run_portable(
        args.source,
        output,
        noise_db=args.noise_db,
        min_silence_ms=args.min_silence_ms,
        min_speech_ms=args.min_speech_ms,
        vad_engine=args.vad_engine,
        speech_threshold=args.speech_threshold,
        speech_pad_before_ms=args.speech_pad_before_ms,
        speech_pad_after_ms=args.speech_pad_after_ms,
        jl=jl,
        zooms=zooms,
        dialect=args.dialect,
        transcript_path=args.transcript,
        cull_retakes=args.cull_retakes,
        transcribe=args.transcribe,
        asr_base_url=args.asr_base_url,
        asr_model=args.asr_model,
        asr_language=args.asr_language,
        whisper_model=args.whisper_model,
        faster_whisper_model=args.faster_whisper_model,
        transcribe_config=TranscribeConfig(
            engine=args.whisper_engine,
            model_size=args.model_size,
            language=args.asr_language,
            device=args.device,
            compute_type=args.compute_type,
            vad_filter=args.whisper_vad,
        ),
        llm_client=client,
        strictness=args.strictness,
        retake_strategy=args.retake_strategy,
        context_window=args.context_window,
        shorts=args.shorts,
        shorts_count=args.shorts_count,
        shorts_min_sec=args.shorts_min_sec,
        shorts_max_sec=args.shorts_max_sec,
        shorts_subtitles=not args.no_shorts_subtitles,
        shorts_config=shorts_config,
        audio_filters=tuple(
            audio_filters(AudioEnhanceConfig(enabled=args.audio_enhance))
        ),
    )
    print(json.dumps(result.to_dict(), indent=2))
    return 0


def _demo(args: argparse.Namespace) -> int:
    ffmpeg = find_binary("ffmpeg")
    if ffmpeg is None:
        print("FFmpeg is not available.", file=sys.stderr)
        return 1
    output = Path(args.out).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = output / "demo-source.mp4"
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=640x360:rate=30",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=6",
        "-af",
        "volume=0:enable='between(t,1,2)+between(t,3,4)'",
        "-t",
        "6",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(source),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        print(completed.stderr.strip(), file=sys.stderr)
        return 1
    result = run_portable(source, output, vad_engine="ffmpeg")
    print(json.dumps(result.to_dict(), indent=2))
    return 0


def _shorts(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser().resolve()
    output = (
        Path(args.out).expanduser().resolve()
        if args.out
        else source.with_name(f"{source.stem}-shorts")
    )
    engine = FFmpegAdapter()
    media = engine.probe(source)
    timebase = media.timebase()
    sentences = parse_srt_file(args.transcript, media.audio_sample_rate)
    cuts: list[tuple[int, int]] = []
    client = None
    if args.llm_base_url:
        from videoflow.adapters.llm import OpenAICompatibleLlm

        client = OpenAICompatibleLlm(
            base_url=args.llm_base_url,
            model=args.llm_model,
            api_key=os.environ.get("VIDEOWFLOW_LLM_API_KEY"),
        )
    culled_ids: set[int] = set()
    if args.cull_retakes:
        culled = cull_transcript_retakes(sentences, client=client)
        culled_ids = set(culled.discard_sentence_ids)
        cuts = cull_intervals(sentences, culled.discard_sentence_ids)
    kept = [item for item in sentences if item.id not in culled_ids]
    if args.end_sec is not None and args.end_sec <= args.start_sec:
        print("--end-sec must be greater than --start-sec.", file=sys.stderr)
        return 2
    range_start = timebase.seconds_to_samples(Fraction(str(args.start_sec)), Rounding.NEAREST)
    range_end = (
        timebase.seconds_to_samples(Fraction(str(args.end_sec)), Rounding.NEAREST)
        if args.end_sec is not None
        else timebase.seconds_to_samples(
            timebase.frames_to_seconds(media.duration_frames), Rounding.NEAREST
        )
    )
    kept = [
        item
        for item in kept
        if item.start_sample >= range_start and item.end_sample <= range_end
    ]
    if not kept:
        print("No sentences remain in the selected source window.", file=sys.stderr)
        return 1
    width, height = short_dimensions(args.aspect)
    minimum = max(1, timebase.seconds_to_samples(Fraction(args.min_sec), Rounding.NEAREST))
    maximum = timebase.seconds_to_samples(Fraction(args.max_sec), Rounding.NEAREST)
    if maximum <= minimum:
        print("--max-sec must be greater than --min-sec.", file=sys.stderr)
        return 2
    warnings: list[str] = []
    scene_intervals_data: tuple[tuple[int, int], ...] = ()
    if args.scene_change:
        scene_intervals_data = tuple(
            scene_intervals(detect_scene_changes(source), sample_rate=media.audio_sample_rate)
        )
    previous = (
        previous_shorts_from_report(output / "shorts.json")
        if args.prompt_mode == "refine"
        else []
    )
    clips = select_shorts(
        kept,
        min_samples=minimum,
        max_samples=maximum,
        count=args.count,
        sample_rate=media.audio_sample_rate,
        cuts=cuts,
        client=client,
        warnings=warnings,
        prompt=args.prompt,
        reprompt=args.reprompt,
        prompt_mode=args.prompt_mode,
        previous=previous,
        hook_mode=args.hook_mode,
        remove_fillers=args.remove_fillers,
        filler_words=args.filler_word,
        scene_intervals=scene_intervals_data,
    )
    if args.reframe in {"motion_tracking", "face_tracking"}:
        from dataclasses import replace as replace_clip

        from videoflow.application.tracking import track_focus_x

        clips = [
            replace_clip(
                clip,
                crop_focus_x=track_focus_x(
                    source,
                    clip.pieces,
                    media.audio_sample_rate,
                    mode=args.reframe,
                )[0],
            )
            for clip in clips
        ]
    if not clips:
        print(json.dumps({"ok": False, "warnings": warnings}, indent=2), file=sys.stderr)
        return 1
    shorts_dir = output / "shorts"
    shorts_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[dict[str, object]] = []
    for index, clip in enumerate(clips, start=1):
        slug = slugify(clip.title, index)
        destination = shorts_dir / f"{slug}.mp4"
        ass_path = None
        if not args.no_subtitles:
            events = sentence_events(kept, clip.pieces, sample_rate=media.audio_sample_rate)
            if events:
                ass_path = shorts_dir / f"{slug}.ass"
                write_text(ass_path, build_ass(events, width=width, height=height))
        engine.render_short(
            source,
            clip.pieces,
            destination,
            sample_rate=media.audio_sample_rate,
            ass_path=ass_path,
            width=width,
            height=height,
            fontsdir=str(fonts_dir()),
            audio_filters=tuple(
                audio_filters(AudioEnhanceConfig(enabled=args.audio_enhance))
            ),
            crop_focus_x=clip.crop_focus_x,
            crop_focus_y=clip.crop_focus_y,
        )
        entry = clip.to_dict(media.audio_sample_rate)
        entry["aspect_ratio"] = args.aspect
        entry["width"] = width
        entry["height"] = height
        entry["path"] = str(destination)
        if ass_path is not None:
            entry["subtitles"] = str(ass_path)
        rendered.append(entry)
    report = {
        "ok": True,
        "source": str(source),
        "transcript": str(Path(args.transcript).expanduser().resolve()),
        "culled_sentence_ids": sorted(culled_ids),
        "clips": rendered,
        "warnings": warnings,
    }
    write_text(output / "shorts.json", json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from videoflow.api.app import create_http_app

    os.environ.setdefault("VIDEOWFLOW_HOME", str(ensure_home()))
    url = _running_service(args.host, args.port)
    if url is not None:
        print(f"VideoFlow is already running at {url}")
        if args.open:
            import webbrowser

            webbrowser.open(url)
        return 0

    print(
        f"VideoFlow {__version__} starting at {_ui_url(args.host, args.port)} "
        "(the portable build can take a few seconds to unpack).",
        flush=True,
    )
    app = create_http_app()
    pid_path = _pid_file()
    _write_pid(pid_path, args.host, args.port)
    opened = False
    try:
        while True:
            config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
            server = uvicorn.Server(config)
            app.state.uvicorn_server = server
            app.state.restart_requested = False
            if args.open and not opened:
                opened = True
                _schedule_browser(_ui_url(args.host, args.port))
            server.run()
            if not bool(getattr(app.state, "restart_requested", False)):
                break
            print("VideoFlow service restarting...")
            app = create_http_app(
                jobs=app.state.jobs,
                projects=app.state.projects,
            )
    finally:
        _remove_pid(pid_path)
    return 0


def _pid_file() -> Path:
    return portable_home() / "server.pid"


def _write_pid(path: Path, host: str, port: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "host": host,
                "port": port,
                "url": _ui_url(host, port),
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _read_pid(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if isinstance(payload, int):
        return {"pid": payload}
    return payload if isinstance(payload, dict) else {}


def _remove_pid(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink()


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _stop(args: argparse.Namespace) -> int:
    path = _pid_file()
    payload = _read_pid(path)
    try:
        pid = int(payload.get("pid", 0))
    except (TypeError, ValueError):
        pid = 0
    if pid <= 0:
        print("VideoFlow service is not running (no PID file).")
        return 0
    if not _process_alive(pid):
        _remove_pid(path)
        print("VideoFlow service is not running (stale PID file removed).")
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        print(f"Could not stop VideoFlow (PID {pid}): {exc}", file=sys.stderr)
        return 1
    deadline = time.monotonic() + max(0.0, float(args.timeout))
    while time.monotonic() < deadline and _process_alive(pid):
        time.sleep(0.1)
    if _process_alive(pid):
        print(f"VideoFlow did not stop within {args.timeout:.1f}s (PID {pid}).", file=sys.stderr)
        return 1
    _remove_pid(path)
    print(f"VideoFlow service stopped (PID {pid}).")
    return 0


def _restart(args: argparse.Namespace) -> int:
    _stop(argparse.Namespace(timeout=5.0))
    time.sleep(0.4)
    return _serve(argparse.Namespace(host=args.host, port=args.port, open=True))


def _status() -> int:
    path = _pid_file()
    payload = _read_pid(path)
    try:
        pid = int(payload.get("pid", 0))
    except (TypeError, ValueError):
        pid = 0
    running = pid > 0 and _process_alive(pid)
    print(
        json.dumps(
            {
                "running": running,
                "pid": pid or None,
                "url": payload.get("url")
                or _ui_url(str(payload.get("host", "127.0.0.1")), int(payload.get("port", 8765))),
            },
            indent=2,
        )
    )
    return 0


def _running_service(host: str, port: int) -> str | None:
    import urllib.error
    import urllib.request

    url = _ui_url(host, port)
    try:
        with urllib.request.urlopen(f"{url}health", timeout=0.6) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    if isinstance(payload, dict) and payload.get("service") == "videoflow":
        return url
    return None


def _ui_url(host: str, port: int) -> str:
    visible = host if host not in {"0.0.0.0", "::"} else "127.0.0.1"
    return f"http://{visible}:{port}/"


def _schedule_browser(url: str) -> None:
    import threading
    import time as _time
    import urllib.error
    import urllib.request
    import webbrowser

    def open_when_ready() -> None:
        deadline = _time.monotonic() + 30.0
        while _time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"{url}health", timeout=0.8) as response:
                    if response.status == 200:
                        webbrowser.open(url)
                        return
            except (OSError, urllib.error.URLError):
                _time.sleep(0.5)
        webbrowser.open(url)

    threading.Thread(target=open_when_ready, daemon=True).start()


def _mcp() -> int:
    from videoflow.mcp_server.server import build_server

    build_server().run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
