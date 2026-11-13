#!/usr/bin/env python
"""Smoke the tray icon and its job controls on a real X display."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _latest_binary() -> Path | None:
    candidates = sorted(
        (ROOT / "releases").glob("v*/videoflow-*-linux-x86_64"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _wait_health(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.25)
    return False


def _post(port: int, path: str) -> dict[str, object]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", method="POST"
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def _icon_window(display_name: str) -> dict[str, object] | None:
    from Xlib import display

    display = display.Display(display_name)
    root = display.screen().root

    def walk(window) -> dict[str, object] | None:
        try:
            attrs = window.get_attributes()
            name = window.get_wm_name()
            wm_class = window.get_wm_class() or ()
            if attrs.map_state == 2 and (
                "videoflow" in str(name).casefold()
                or any("videoflow" in str(item).casefold() for item in wm_class)
            ):
                geometry = window.get_geometry()
                return {
                    "id": hex(window.id),
                    "name": str(name or ""),
                    "class": [str(item) for item in wm_class],
                    "width": geometry.width,
                    "height": geometry.height,
                }
        except Exception:  # noqa: BLE001 - stale X windows are common
            pass
        try:
            for child in window.query_tree().children:
                found = walk(child)
                if found is not None:
                    return found
        except Exception:  # noqa: BLE001
            pass
        return None

    try:
        return walk(root)
    finally:
        display.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=None)
    parser.add_argument("--port", type=int, default=8891)
    parser.add_argument("--display", default=os.environ.get("DISPLAY", ""))
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    binary = (args.binary or _latest_binary())
    if binary is None or not binary.is_file():
        print(json.dumps({"ok": False, "error": "binary not found"}, indent=2))
        return 2
    if not args.display:
        print(json.dumps({"ok": False, "error": "DISPLAY is not set"}, indent=2))
        return 2

    env = {**os.environ, "DISPLAY": args.display}
    env.pop("PYSTRAY_BACKEND", None)
    process = subprocess.Popen(
        [
            str(binary),
            "tray",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.port),
            "--no-open",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    icon: dict[str, object] | None = None
    controls: dict[str, object] = {}
    error = ""
    try:
        if not _wait_health(args.port, args.timeout):
            error = "server did not answer /health"
        else:
            deadline = time.time() + 10.0
            while time.time() < deadline and icon is None:
                icon = _icon_window(args.display)
                if icon is None:
                    time.sleep(0.25)
            if icon is None:
                error = "tray icon window was not found on the X display"
            else:
                for name, path in (
                    ("pause_all", "/api/v1/jobs/pause_all"),
                    ("resume_all", "/api/v1/jobs/resume_all"),
                    ("cancel_all", "/api/v1/jobs/cancel_all"),
                ):
                    try:
                        controls[name] = _post(args.port, path)
                    except Exception as exc:  # noqa: BLE001
                        controls[name] = {"ok": False, "error": str(exc)}
    finally:
        stderr = ""
        with contextlib.suppress(OSError):
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        try:
            _, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError):
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            _, stderr = process.communicate(timeout=10)

    payload = {
        "ok": icon is not None and not error,
        "binary": str(binary),
        "display": args.display,
        "icon": icon,
        "controls": controls,
        "error": error,
        "stderr": stderr[-2000:],
    }
    print(json.dumps(payload, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
