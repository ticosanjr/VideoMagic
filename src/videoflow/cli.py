"""Unified VideoFlow CLI. This is the single entry point used by the portable build."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from videoflow import __version__
from videoflow.application.portable import run_portable
from videoflow.domain.config import JlCutsConfig, ZoomsConfig
from videoflow.domain.errors import VideoFlowError
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
    run.add_argument("--no-jcuts", action="store_true", help="Disable J-cuts.")
    run.add_argument("--l-cuts", action="store_true", help="Enable L-cuts.")
    run.add_argument("--no-zooms", action="store_true", help="Disable punch-ins.")
    run.add_argument("--offset-ms", type=int, default=200)
    run.add_argument("--crossfade-ms", type=int, default=20)
    run.add_argument("--dialect", choices=("1.9", "1.10"), default="1.9")

    demo = sub.add_parser("demo", help="Generate a fixture and run the full pipeline.")
    demo.add_argument("-o", "--out", type=Path, default=Path("videoflow-demo"))

    serve = sub.add_parser("serve", help="Serve the API, MCP HTTP, and rack UI.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

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
    result = run_portable(
        args.source,
        output,
        noise_db=args.noise_db,
        min_silence_ms=args.min_silence_ms,
        jl=jl,
        zooms=zooms,
        dialect=args.dialect,
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


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    os.environ.setdefault("VIDEOWFLOW_HOME", str(ensure_home()))
    uvicorn.run(
        "videoflow.api.app:create_http_app",
        factory=True,
        host=args.host,
        port=args.port,
    )
    return 0


def _mcp() -> int:
    from videoflow.mcp_server.server import build_server

    build_server().run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
