"""Smoke the built AppImage end to end.

Checks version, doctor, demo, direct extraction fallback, and the no-argument
desktop behavior (starts the local server and answers /health).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--appimage", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "smoke-appimage")
    parser.add_argument("--port", type=int, default=8897)
    args = parser.parse_args()
    appimage = args.appimage or _latest()
    if appimage is None or not appimage.is_file():
        print("AppImage not found")
        return 1
    args.out.mkdir(parents=True, exist_ok=True)

    _run([str(appimage), "version"])
    _run([str(appimage), "doctor"])
    report = args.out / "demo.json"
    _run([str(appimage), "demo", "-o", str(args.out / "demo")], stdout=report)
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["ok"] is True, payload
    assert set(payload["artifacts"]) == {"resolve", "premiere", "kdenlive"}

    env = dict(os.environ)
    env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
    _run([str(appimage), "version"], env=env)

    process = subprocess.Popen(
        [str(appimage), "serve", "--port", str(args.port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_health(args.port)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    print("PASS: AppImage version, doctor, demo, extract-run, and serve")
    return 0


def _run(
    command: list[str], *, env: dict[str, str] | None = None, stdout: Path | None = None
) -> None:
    target = stdout.open("w", encoding="utf-8") if stdout else None
    try:
        completed = subprocess.run(
            command,
            check=False,
            env=env,
            stdout=target,
            stderr=subprocess.PIPE,
            text=True,
        )
    finally:
        if target:
            target.close()
    if completed.returncode != 0:
        print(completed.stderr, file=sys.stderr)
        raise SystemExit(f"failed: {' '.join(command)}")


def _wait_health(port: int) -> None:
    url = f"http://127.0.0.1:{port}/health"
    for _ in range(60):
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.5)
    raise SystemExit("server did not answer /health")


def _latest() -> Path | None:
    candidates = sorted(
        (ROOT / "releases").glob("v*/VideoFlow-*-x86_64.AppImage"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


if __name__ == "__main__":
    raise SystemExit(main())
