"""Smoke-test a frozen VideoFlow executable on Windows (also runnable on Linux).

The check runs with a clean ``PATH`` so it proves the portable bundle is
self-contained: ``version``, ``doctor`` (FFmpeg, Windows fonts, CUDA/NVENC),
``mcp --profile core --list-tools``, and a temporary ``serve`` process started
on an already-occupied port. The server must fall back to the next bindable
port, publish ``active_server.json``, and answer ``/`` plus
``/api/v1/curation/boards``. Automatic model downloads stay disabled for the
whole smoke run. The server is always stopped in a ``finally`` block.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

CORE_TOOLS = (
    "vf_style",
    "vf_curation",
    "vf_decupage",
    "vf_shorts",
    "vf_export",
)
_DROP_ENV = {
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONSTARTUP",
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
    "UV_PROJECT_ENVIRONMENT",
}


class SmokeError(RuntimeError):
    """A smoke assertion failed."""


def default_exe() -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    onedir = Path("dist") / "videoflow" / f"videoflow{suffix}"
    if onedir.is_file():
        return onedir
    return Path("dist") / f"videoflow{suffix}"


def clean_env(home: Path, *, keep_path: bool = False) -> dict[str, str]:
    """Environment for the frozen executable, without the build environment."""

    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in _DROP_ENV and key.upper() != "PATH"
    }
    if keep_path:
        env["PATH"] = os.environ.get("PATH", "")
    elif os.name == "nt":
        windir = Path(env.get("SYSTEMROOT", os.environ.get("SYSTEMROOT", r"C:\Windows")))
        env["PATH"] = os.pathsep.join((str(windir / "System32"), str(windir)))
    else:
        env["PATH"] = os.pathsep.join(("/usr/bin", "/bin"))
    env["VIDEOWFLOW_HOME"] = str(home)
    env["VIDEOWFLOW_ALLOWED_ROOTS"] = str(home)
    env["VIDEOWFLOW_NO_AUTO_DOWNLOAD"] = "1"
    env.pop("VIDEOWFLOW_ASR_AUTO_DOWNLOAD", None)
    env.pop("VIDEOWFLOW_AUTO_DOWNLOAD", None)
    env.pop("VF_GPU_WORKER_URL", None)
    return env


def run(
    exe: Path,
    args: list[str],
    *,
    env: dict[str, str],
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(exe), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )


def _json_output(text: str) -> dict[str, object]:
    payload = text.strip()
    start = payload.find("{")
    if start > 0:
        payload = payload[start:]
    try:
        value = json.loads(payload)
    except ValueError as exc:
        raise SmokeError(f"expected JSON output, got: {text[-500:]}") from exc
    if not isinstance(value, dict):
        raise SmokeError("expected a JSON object")
    return value


def check_version(exe: Path, env: dict[str, str], timeout: float) -> str:
    completed = run(exe, ["version"], env=env, timeout=timeout)
    if completed.returncode != 0:
        raise SmokeError(f"version failed ({completed.returncode}): {completed.stderr}")
    output = completed.stdout.strip()
    if "videoflow" not in output.casefold():
        raise SmokeError(f"version output is not VideoFlow: {output!r}")
    print(f"[ok] version: {output}")
    return output


def check_doctor(exe: Path, env: dict[str, str], timeout: float) -> dict[str, object]:
    completed = run(exe, ["doctor"], env=env, timeout=timeout)
    payload = _json_output(completed.stdout)
    if completed.returncode != 0 or not payload.get("ok"):
        raise SmokeError(
            "doctor failed: "
            + json.dumps(
                {key: payload.get(key) for key in ("ok", "ffmpeg", "ffprobe", "mcp")},
                ensure_ascii=False,
            )
        )
    for name in ("ffmpeg", "ffprobe"):
        entry = payload.get(name)
        if not isinstance(entry, dict) or not entry.get("found"):
            raise SmokeError(f"doctor did not find bundled {name}: {entry!r}")
        path = str(entry.get("path") or "")
        if os.name == "nt" and not path.casefold().endswith(".exe"):
            raise SmokeError(f"doctor resolved {name} outside the bundle: {path!r}")
    ui = payload.get("ui")
    if not ui:
        raise SmokeError("doctor did not find the bundled UI")
    fonts = payload.get("fonts")
    if not isinstance(fonts, dict) or not fonts.get("dirs"):
        raise SmokeError(f"doctor did not report system fonts: {fonts!r}")
    cuda = payload.get("cuda")
    if not isinstance(cuda, dict) or "devices" not in cuda:
        raise SmokeError(f"doctor did not report CUDA status: {cuda!r}")
    nvenc = payload.get("nvenc")
    if not isinstance(nvenc, dict) or not isinstance(nvenc.get("available"), bool):
        raise SmokeError(f"doctor did not report NVENC status: {nvenc!r}")
    print(
        "[ok] doctor: ffmpeg/ffprobe, ui, "
        f"{fonts.get('count')} font dirs, cuda={cuda.get('devices')}, "
        f"nvenc={nvenc.get('available')}"
    )
    return payload


def check_mcp_tools(exe: Path, env: dict[str, str], timeout: float) -> list[str]:
    completed = run(
        exe,
        ["mcp", "--profile", "core", "--list-tools"],
        env=env,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise SmokeError(f"mcp --list-tools failed: {completed.stderr}")
    tools = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    missing = [name for name in CORE_TOOLS if name not in tools]
    if missing:
        raise SmokeError(f"core profile is missing tools: {', '.join(missing)}")
    print(f"[ok] mcp core profile: {len(tools)} tools, {', '.join(CORE_TOOLS)}")
    return tools


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def http_json(url: str, *, timeout: float = 2.0) -> tuple[int, dict[str, object]]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        status = int(response.status)
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise SmokeError(f"expected JSON from {url}")
    return status, payload


def check_ui_assets(base: str, *, timeout: float) -> str:
    with urllib.request.urlopen(f"{base}/", timeout=timeout) as response:
        html = response.read().decode("utf-8", errors="replace")
    if "<html" not in html.casefold() or "VideoFlow" not in html:
        raise SmokeError(f"GET / did not return the built UI: {html[:300]!r}")
    import re

    match = re.search(r'(?:src|href)="([^"]+\.js[^"]*)"', html)
    if match is None:
        raise SmokeError(f"the UI HTML has no JavaScript asset: {html[:500]!r}")
    from urllib.parse import urljoin

    path = match.group(1)
    url = path if path.startswith("http") else urljoin(base + "/", path)
    with urllib.request.urlopen(url, timeout=timeout) as response:
        status = int(response.status)
        asset = response.read()
    if status != 200 or len(asset) < 100:
        raise SmokeError(f"UI asset {path} did not load")
    print(f"[ok] ui: / and {path} returned 200")
    return path


def _bundled_ffmpeg(exe: Path) -> Path | None:
    names = {"ffmpeg.exe"} if os.name == "nt" else {"ffmpeg"}
    for path in exe.parent.rglob("*"):
        if path.is_file() and path.name.casefold() in names:
            return path
    return None


def check_synthetic_job(
    exe: Path,
    env: dict[str, str],
    home: Path,
    timeout: float,
) -> None:
    ffmpeg = _bundled_ffmpeg(exe)
    if ffmpeg is None:
        print("[skip] synthetic job: bundled ffmpeg was not found")
        return
    source = home / "synthetic.mp4"
    recipe = home / "synthetic-recipe.json"
    completed = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x180:r=30:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SmokeError(f"cannot create the synthetic source: {completed.stderr[-800:]}")
    recipe.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "smoke_ingest",
                "name": "Smoke ingest",
                "steps": [
                    {
                        "id": "ingest",
                        "type": "ingest",
                        "params": {"extract_pcm": True},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = run(
        exe,
        [
            "recipe",
            "run",
            str(recipe),
            str(source),
            "-o",
            str(home / "synthetic-project"),
            "--json",
            "--force",
        ],
        env=env,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise SmokeError(f"synthetic job failed: {result.stderr[-1200:]}")
    payload = _json_output(result.stdout)
    if payload.get("ok") is False:
        raise SmokeError(f"synthetic job returned a failure: {payload}")
    print("[ok] synthetic job: ingest recipe completed")


def wait_for_server(
    exe: Path,
    *,
    env: dict[str, str],
    port: int,
    timeout: float,
    log_path: Path,
) -> None:
    command = [
        str(exe),
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=str(exe.parent),
        )
        passed = False
        try:
            base = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + timeout
            last_error = ""
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    last_error = f"serve exited with {process.returncode}"
                    break
                try:
                    status, payload = http_json(f"{base}/health")
                    if status == 200 and payload.get("service") == "videoflow":
                        break
                except (OSError, ValueError, urllib.error.URLError) as exc:
                    last_error = str(exc)
                time.sleep(0.25)
            else:
                raise SmokeError(f"serve did not become ready: {last_error}")
            if process.poll() is not None:
                raise SmokeError(
                    "serve exited before /health was ready: " + _tail(log_path)
                )
            status, payload = http_json(f"{base}/health")
            if status != 200 or payload.get("service") != "videoflow":
                raise SmokeError(f"unexpected /health payload: {payload!r}")
            status, boards = http_json(f"{base}/api/v1/curation/boards")
            if status != 200 or boards.get("ok") is not True:
                raise SmokeError(f"unexpected curation boards payload: {boards!r}")
            check_ui_assets(base, timeout=timeout)
            print(
                "[ok] serve: /health and /api/v1/curation/boards returned 200 "
                f"({len(boards.get('boards') or [])} boards)"
            )
            passed = True
        finally:
            stop_process(process)
            if not passed:
                print(
                    "serve log:\n" + _tail(log_path, lines=40),
                    file=sys.stderr,
                )


def check_auto_download_disabled(home: Path) -> None:
    """Assert the smoke home has no running bootstrap download job."""

    import sqlite3

    database = home / "videoflow.db"
    if not database.is_file():
        return
    try:
        with sqlite3.connect(database) as connection:
            rows = connection.execute("SELECT payload FROM jobs").fetchall()
    except sqlite3.Error:
        return
    for (raw,) in rows:
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        if (
            payload.get("origin") == "bootstrap"
            and payload.get("status") in {"queued", "running"}
        ):
            raise SmokeError(
                "VIDEOWFLOW_NO_AUTO_DOWNLOAD=1 was ignored: "
                f"bootstrap job {payload.get('job_id')} is still running"
            )
    print("[ok] models: auto-download disabled")


def check_port_fallback(
    exe: Path,
    *,
    env: dict[str, str],
    home: Path,
    occupied_port: int,
    timeout: float,
) -> None:
    """Occupy the requested port and prove serve picks the next one."""

    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(("127.0.0.1", int(occupied_port)))
    occupied.listen(1)
    log_path = home / "serve-fallback.log"
    command = [
        str(exe),
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        str(int(occupied_port)),
    ]
    process: subprocess.Popen[bytes] | None = None
    try:
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=str(exe.parent),
            )
        deadline = time.monotonic() + timeout
        real_port = 0
        base = ""
        last_error = ""
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise SmokeError(
                    f"serve exited with {process.returncode} before the fallback port"
                )
            try:
                payload = json.loads(
                    (home / "active_server.json").read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                payload = {}
            try:
                candidate = int(payload.get("port") or 0)
            except (TypeError, ValueError):
                candidate = 0
            if candidate and candidate != int(occupied_port):
                candidate_base = f"http://127.0.0.1:{candidate}"
                try:
                    status, health = http_json(f"{candidate_base}/health")
                except (OSError, ValueError, urllib.error.URLError) as exc:
                    last_error = str(exc)
                else:
                    if status == 200 and health.get("service") == "videoflow":
                        real_port = candidate
                        base = candidate_base
                        break
            time.sleep(0.25)
        if not real_port:
            raise SmokeError(
                f"serve did not fall back from port {occupied_port}: {last_error}"
            )
        status, boards = http_json(f"{base}/api/v1/curation/boards")
        if status != 200 or boards.get("ok") is not True:
            raise SmokeError(f"unexpected curation boards payload: {boards!r}")
        check_ui_assets(base, timeout=timeout)
        check_auto_download_disabled(home)
        print(
            f"[ok] serve: occupied {occupied_port}, started on {real_port}; "
            f"/ and /api/v1/curation/boards returned 200"
        )
    finally:
        if process is not None:
            stop_process(process)
        occupied.close()


def stop_process(process: subprocess.Popen[bytes]) -> None:
    """Stop the serve process and its children, without leaving the runner stuck."""

    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            process.kill()
        process.wait(timeout=10)


def _tail(path: Path, *, lines: int = 20) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(content[-lines:])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test a frozen VideoFlow executable with a clean PATH."
    )
    parser.add_argument(
        "--exe",
        type=Path,
        default=None,
        help="Path to videoflow.exe (default: dist/videoflow/videoflow.exe).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Port for the temporary serve process (0 picks a free port).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Seconds to wait for each command and for serve readiness.",
    )
    parser.add_argument(
        "--keep-path",
        action="store_true",
        help="Keep the current PATH (useful when testing a source wrapper).",
    )
    parser.add_argument(
        "--keep-home",
        action="store_true",
        help="Keep the temporary home directory after the run for inspection.",
    )
    args = parser.parse_args(argv)

    exe = (args.exe or default_exe()).expanduser().resolve()
    if not exe.is_file():
        print(f"executable not found: {exe}", file=sys.stderr)
        return 2
    if os.name == "nt" and exe.suffix.casefold() != ".exe":
        print(f"expected a .exe on Windows: {exe}", file=sys.stderr)
        return 2

    home_dir = tempfile.mkdtemp(prefix="videoflow-smoke-")
    home = Path(home_dir)
    env = clean_env(home, keep_path=args.keep_path)
    try:
        print(f"smoke target: {exe}")
        check_version(exe, env, args.timeout)
        check_doctor(exe, env, args.timeout)
        check_mcp_tools(exe, env, args.timeout)
        check_port_fallback(
            exe,
            env=env,
            home=home,
            occupied_port=args.port or free_port(),
            timeout=args.timeout,
        )
        check_synthetic_job(exe, env, home, args.timeout)
    except SmokeError as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        return 1
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        return 1
    finally:
        if not args.keep_home:
            import shutil

            shutil.rmtree(home, ignore_errors=True)
    print("[ok] portable smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
