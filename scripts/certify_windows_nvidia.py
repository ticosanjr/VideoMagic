"""Certify a published Windows/NVIDIA VideoFlow binary end to end.

This is an operator tool, not part of the runtime. It drives the built binary
with a clean PATH and writes JSON/Markdown evidence under docs/qa-evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "qa-evidence"
DROPPED_ENV = {
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONSTARTUP",
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
    "UV_PROJECT_ENVIRONMENT",
}


class CertifyError(RuntimeError):
    """One certification step failed."""


def clean_env(home: Path) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in DROPPED_ENV and key.upper() != "PATH"
    }
    if os.name == "nt":
        windir = Path(env.get("SYSTEMROOT", r"C:\Windows"))
        env["PATH"] = os.pathsep.join((str(windir / "System32"), str(windir)))
    else:
        env["PATH"] = os.pathsep.join(("/usr/bin", "/bin"))
    env["VIDEOWFLOW_HOME"] = str(home)
    env["VIDEOWFLOW_ALLOWED_ROOTS"] = str(home)
    env.pop("VF_GPU_WORKER_URL", None)
    return env


def run(
    binary: Path,
    args: list[str],
    *,
    env: dict[str, str],
    timeout: float,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [str(binary), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )
    if check and completed.returncode != 0:
        raise CertifyError(
            f"{' '.join(args)} failed ({completed.returncode}): "
            f"{completed.stderr[-1500:]}"
        )
    return completed


def json_output(text: str) -> dict[str, Any]:
    payload = text.strip()
    start = payload.find("{")
    if start > 0:
        payload = payload[start:]
    try:
        value = json.loads(payload)
    except ValueError as exc:
        raise CertifyError(f"expected JSON output: {text[-1000:]}") from exc
    if not isinstance(value, dict):
        raise CertifyError("expected a JSON object")
    return value


def http(url: str, *, timeout: float = 5.0) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return int(response.status), response.read().decode("utf-8", errors="replace")


def http_json(url: str, *, timeout: float = 5.0) -> dict[str, Any]:
    status, body = http(url, timeout=timeout)
    if status != 200:
        raise CertifyError(f"{url} returned HTTP {status}")
    return json.loads(body)


def find_ffmpeg(binary: Path) -> str | None:
    names = {"ffmpeg.exe", "ffmpeg"} if os.name == "nt" else {"ffmpeg"}
    for path in binary.parent.rglob("*"):
        if path.is_file() and path.name.casefold() in names:
            return str(path)
    return None


def synthetic_video(ffmpeg: str, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=320x180:r=30:d=2",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=2",
        "-c:v",
        "prores_ks",
        "-profile:v",
        "3",
        "-pix_fmt",
        "yuv422p10le",
        "-c:a",
        "pcm_s16le",
        "-shortest",
        str(target),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise CertifyError(f"cannot create the 10-bit fixture: {completed.stderr[-1000:]}")
    return target


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def occupied_socket(port: int) -> socket.socket:
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", port))
    holder.listen(1)
    return holder


def start_server(
    binary: Path,
    *,
    env: dict[str, str],
    port: int,
    home: Path,
    log_path: Path,
) -> subprocess.Popen[bytes]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [
                str(binary),
                "serve",
                "--mcp-only",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=str(binary.parent),
        )
    return process


def stop_server(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def wait_ready(base: str, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            payload = http_json(f"{base}/health")
            if payload.get("service") == "videoflow":
                return
        except (OSError, ValueError, CertifyError) as exc:
            last = str(exc)
        time.sleep(0.25)
    raise CertifyError(f"{base} did not become ready: {last}")


def active_port(home: Path, *, timeout: float) -> int:
    path = home / "active_server.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            port = int(payload.get("port") or 0)
            if port > 0:
                return port
        except (OSError, ValueError, TypeError):
            pass
        time.sleep(0.2)
    raise CertifyError("active_server.json did not expose the selected port")


def check_doctor(binary: Path, env: dict[str, str], timeout: float) -> dict[str, Any]:
    payload = json_output(run(binary, ["doctor"], env=env, timeout=timeout).stdout)
    if not payload.get("ok"):
        raise CertifyError("doctor is not ok")
    cuda = payload.get("cuda") or {}
    nvenc = payload.get("nvenc") or {}
    if not int(cuda.get("devices") or 0):
        raise CertifyError(f"CUDA has no visible device: {cuda}")
    if not nvenc.get("available"):
        raise CertifyError(f"NVENC is unavailable: {nvenc}")
    matrix = payload.get("feature_matrix")
    if not isinstance(matrix, list) or not matrix:
        raise CertifyError("doctor did not return feature_matrix")
    return payload


def check_tray(binary: Path, env: dict[str, str], timeout: float) -> dict[str, Any]:
    completed = run(binary, ["tray", "--check"], env=env, timeout=timeout, check=False)
    try:
        payload = json.loads(completed.stdout)
    except ValueError as exc:
        raise CertifyError(
            f"tray --check did not return JSON: {completed.stderr[-800:]}"
        ) from exc
    if completed.returncode != 0 or not payload.get("available"):
        raise CertifyError(f"tray backend is unavailable: {payload}")
    return payload


def check_server_and_ui(
    binary: Path,
    env: dict[str, str],
    home: Path,
    timeout: float,
) -> dict[str, Any]:
    requested = free_port()
    holder = occupied_socket(requested)
    log_path = home / "cert-serve.log"
    process = start_server(
        binary, env=env, port=requested, home=home, log_path=log_path
    )
    second: subprocess.Popen[bytes] | None = None
    try:
        actual = active_port(home, timeout=timeout)
        if actual == requested:
            raise CertifyError("serve ignored the occupied port")
        base = f"http://127.0.0.1:{actual}"
        wait_ready(base, timeout=timeout)
        _, html = http(f"{base}/", timeout=timeout)
        if "_app/immutable" not in html and "<div id=" not in html:
            raise CertifyError("GET / did not return the built UI")
        match = re.search(r'(?:src|href)="([^"]+\.js[^"]*)"', html)
        if match is None:
            raise CertifyError("the UI HTML has no JavaScript asset")
        match_path = match.group(1)
        asset_url = match_path if match_path.startswith("http") else base + match_path
        status, asset = http(asset_url, timeout=timeout)
        if status != 200 or len(asset) < 100:
            raise CertifyError(f"UI asset {match_path} did not load")
        second_port = free_port()
        second = start_server(
            binary,
            env=env,
            port=second_port,
            home=home,
            log_path=home / "cert-serve-2.log",
        )
        second_base = f"http://127.0.0.1:{second_port}"
        wait_ready(second_base, timeout=timeout)
        boards_first = http_json(f"{base}/api/v1/curation/boards", timeout=timeout)
        boards_second = http_json(
            f"{second_base}/api/v1/curation/boards",
            timeout=timeout,
        )
        if boards_first.get("ok") is not True or boards_second.get("ok") is not True:
            raise CertifyError("cross-process curation boards did not load")
        return {
            "requested_port": requested,
            "actual_port": actual,
            "second_port": second_port,
            "ui_asset": match_path,
            "cross_process_boards": len(boards_first.get("boards") or []),
        }
    finally:
        stop_server(process)
        if second is not None:
            stop_server(second)
        holder.close()


def recipe_payload(mode: str) -> dict[str, Any]:
    from videoflow.engine.recipes import builtin_recipe

    recipe = builtin_recipe("youtube_talking_head").model_dump(mode="json")
    steps = [step for step in recipe["steps"] if step.get("type") != "export.nle"]
    for step in steps:
        if step.get("type") == "audio.vad":
            step.setdefault("params", {})["min_silence_ms"] = 220
        if step.get("type") == "transcribe":
            step.setdefault("params", {}).update(
                {"mode": "auto", "device": "cuda"}
            )
        if step.get("type") == "speech.editorial_clean":
            step.setdefault("params", {}).update(
                {"second_pass": True, "max_discard_ratio": 0.75}
            )
        if step.get("type") == "retakes.cull":
            step.setdefault("params", {}).update(
                {"max_discard_ratio": 0.75, "max_group_span_seconds": 420}
            )
    steps.append(
        {
            "id": "export_video",
            "type": "export.video",
            "needs": ["timeline"],
            "params": {"mode": mode, "fps": 30},
        }
    )
    recipe["steps"] = steps
    recipe["id"] = f"certify_{mode}"
    recipe["name"] = f"Certify {mode}"
    return recipe


def run_recipe(
    binary: Path,
    source: Path,
    output: Path,
    *,
    mode: str,
    env: dict[str, str],
    timeout: float,
) -> Path:
    recipe_path = output.with_name(f"certify_{mode}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    recipe_path.write_text(
        json.dumps(recipe_payload(mode), indent=2) + "\n", encoding="utf-8"
    )
    completed = run(
        binary,
        [
            "recipe",
            "run",
            str(recipe_path),
            str(source),
            "-o",
            str(output),
            "--json",
            "--force",
        ],
        env=env,
        timeout=timeout,
    )
    payload = json_output(completed.stdout)
    if payload.get("ok") is False:
        raise CertifyError(f"{mode} recipe failed: {payload}")
    expected = "preview_fast.mp4" if mode == "preview" else None
    exports = output / "exports"
    if expected:
        path = exports / expected
        if not path.is_file():
            raise CertifyError(f"{mode} did not write {expected}")
        return path
    matches = sorted(exports.glob("*.mp4")) if exports.is_dir() else []
    if not matches:
        raise CertifyError("final export wrote no MP4")
    return matches[-1]


def write_evidence(report: dict[str, Any], target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "windows-nvidia-cert.json"
    md_path = target / "windows-nvidia-cert.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Windows / NVIDIA certification",
        "",
        f"- status: **{report.get('status')}**",
        f"- binary: `{report.get('binary', '')}`",
        f"- version: `{report.get('version', '')}`",
        f"- host: `{report.get('host', '')}`",
        "",
        "## Steps",
        "",
    ]
    for item in report.get("steps", []):
        lines.append(
            f"- {item.get('name')}: **{item.get('status')}**"
            + (f" — {item.get('detail')}" if item.get("detail") else "")
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"evidence: {json_path}")
    print(f"evidence: {md_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Certify a Windows/NVIDIA VideoFlow binary end to end."
    )
    parser.add_argument("--binary", type=Path, required=True, help="videoflow.exe")
    parser.add_argument("--video", type=Path, default=None, help="10-bit 4:2:2 footage")
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument(
        "--evidence",
        type=Path,
        default=EVIDENCE,
        help="Directory for the JSON/Markdown report.",
    )
    parser.add_argument("--keep-home", action="store_true")
    args = parser.parse_args(argv)

    binary = args.binary.expanduser().resolve()
    if not binary.is_file():
        print(f"binary not found: {binary}", file=sys.stderr)
        return 2
    home = Path(tempfile.mkdtemp(prefix="videoflow-cert-"))
    env = clean_env(home)
    report: dict[str, Any] = {
        "status": "failed",
        "binary": str(binary),
        "host": os.environ.get("COMPUTERNAME") or socket.gethostname(),
        "steps": [],
    }
    try:
        doctor = check_doctor(binary, env, args.timeout)
        report["version"] = str(doctor.get("version") or "")
        report["steps"].append({"name": "doctor", "status": "passed"})
        tray = check_tray(binary, env, args.timeout)
        report["steps"].append(
            {
                "name": "tray",
                "status": "passed",
                "detail": str(tray.get("backend") or tray.get("reason") or ""),
            }
        )
        server = check_server_and_ui(binary, env, home, args.timeout)
        report["steps"].append(
            {
                "name": "serve/ui/cross-process",
                "status": "passed",
                "detail": json.dumps(server),
            }
        )
        source = args.video
        if source is None:
            ffmpeg = find_ffmpeg(binary)
            if ffmpeg is None:
                raise CertifyError("no --video and no bundled ffmpeg for the fixture")
            source = synthetic_video(ffmpeg, home / "fixture-10bit422.mov")
        preview = run_recipe(
            binary, source, home / "preview", mode="preview", env=env, timeout=args.timeout
        )
        report["steps"].append(
            {"name": "preview export", "status": "passed", "detail": str(preview)}
        )
        final = run_recipe(
            binary, source, home / "final", mode="final", env=env, timeout=args.timeout
        )
        report["steps"].append(
            {"name": "final export", "status": "passed", "detail": str(final)}
        )
        report["status"] = "passed"
    except (CertifyError, OSError, subprocess.SubprocessError, ValueError) as exc:
        report["steps"].append(
            {"name": "failure", "status": "failed", "detail": str(exc)}
        )
        print(f"[fail] {exc}", file=sys.stderr)
    finally:
        write_evidence(report, args.evidence)
        if not args.keep_home:
            import shutil

            shutil.rmtree(home, ignore_errors=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
