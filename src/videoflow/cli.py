"""Unified VideoFlow CLI. This is the single entry point used by the portable build."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path

from videoflow import __version__
from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.portable import run_portable
from videoflow.application.retakes import cull_intervals
from videoflow.application.retakes import cull_retakes as cull_transcript_retakes
from videoflow.application.shorts import (
    build_ass,
    select_shorts,
    sentence_events,
    slugify,
)
from videoflow.domain.config import JlCutsConfig, ZoomsConfig
from videoflow.domain.errors import VideoFlowError
from videoflow.domain.timebase import Rounding
from videoflow.domain.transcript import parse_srt_file
from videoflow.exporters.common import write_text
from videoflow.runtime import ensure_home, find_binary, portable_home, ui_dir


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
    run.add_argument("--no-jcuts", action="store_true", help="Disable J-cuts.")
    run.add_argument("--l-cuts", action="store_true", help="Enable L-cuts.")
    run.add_argument("--no-zooms", action="store_true", help="Disable punch-ins.")
    run.add_argument("--offset-ms", type=int, default=200)
    run.add_argument("--crossfade-ms", type=int, default=20)
    run.add_argument("--dialect", choices=("1.9", "1.10"), default="1.9")
    run.add_argument("--transcript", type=Path, default=None, help="SRT subtitle file.")
    run.add_argument(
        "--transcribe",
        action="store_true",
        help="Use an OpenAI-compatible speech-to-text endpoint when no SRT is given.",
    )
    run.add_argument(
        "--asr-base-url",
        default=os.environ.get("VIDEOWFLOW_ASR_BASE_URL"),
        help="ASR base URL. Defaults to VIDEOWFLOW_ASR_BASE_URL.",
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
    )
    zooms = ZoomsConfig(mode="manual_rules" if args.no_zooms else "alternate_cuts")
    if args.cull_retakes and args.transcript is None:
        print("--cull-retakes requires --transcript.", file=sys.stderr)
        return 2
    client = None
    if args.transcript is not None and args.llm_base_url:
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
        jl=jl,
        zooms=zooms,
        dialect=args.dialect,
        transcript_path=args.transcript,
        cull_retakes=args.cull_retakes,
        transcribe=args.transcribe,
        asr_base_url=args.asr_base_url,
        asr_model=args.asr_model,
        asr_language=args.asr_language,
        llm_client=client,
        strictness=args.strictness,
        retake_strategy=args.retake_strategy,
        context_window=args.context_window,
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
    result = run_portable(source, output)
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
    if not kept:
        print("Retake culling removed every sentence.", file=sys.stderr)
        return 1
    minimum = max(1, timebase.seconds_to_samples(Fraction(args.min_sec), Rounding.NEAREST))
    maximum = timebase.seconds_to_samples(Fraction(args.max_sec), Rounding.NEAREST)
    if maximum <= minimum:
        print("--max-sec must be greater than --min-sec.", file=sys.stderr)
        return 2
    warnings: list[str] = []
    clips = select_shorts(
        kept,
        min_samples=minimum,
        max_samples=maximum,
        count=args.count,
        sample_rate=media.audio_sample_rate,
        cuts=cuts,
        client=client,
        warnings=warnings,
    )
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
                write_text(ass_path, build_ass(events))
        engine.render_short(
            source,
            clip.pieces,
            destination,
            sample_rate=media.audio_sample_rate,
            ass_path=ass_path,
        )
        entry = clip.to_dict(media.audio_sample_rate)
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

    os.environ.setdefault("VIDEOWFLOW_HOME", str(ensure_home()))
    if args.open:
        _schedule_browser(_ui_url(args.host, args.port))
    uvicorn.run(
        "videoflow.api.app:create_http_app",
        factory=True,
        host=args.host,
        port=args.port,
    )
    return 0


def _ui_url(host: str, port: int) -> str:
    visible = host if host not in {"0.0.0.0", "::"} else "127.0.0.1"
    return f"http://{visible}:{port}/"


def _schedule_browser(url: str) -> None:
    import threading
    import webbrowser

    threading.Timer(1.5, lambda: webbrowser.open(url)).start()


def _mcp() -> int:
    from videoflow.mcp_server.server import build_server

    build_server().run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
