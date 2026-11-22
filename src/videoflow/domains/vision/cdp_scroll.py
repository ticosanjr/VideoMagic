"""Chromium CDP scroll capture for URL screenshots and clips."""

from __future__ import annotations

import contextlib
import json
import shutil
import tempfile
from typing import Any

from ..toolkit.errors import MissingCommandError, OutputNotProducedError
from .browser import _chrome


@contextlib.contextmanager
def _cdp_scroll_capture(
    url: str,
    *,
    width: int,
    height: int,
    selector: str = "",
    scroll_animation: str = "",
    clip_selector: str = "",
):
    """Drive Chromium through CDP so URL captures can actually scroll."""

    import base64
    import contextlib as _contextlib
    import socket
    import subprocess
    import time
    import urllib.request

    try:
        import websocket  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001 - optional automation dependency
        raise MissingCommandError(
            "scroll_animation requires websocket-client",
            details={"env": ["VF_CHROME_BIN"], "capability": "scroll"},
        ) from exc

    browser = _chrome()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    profile = tempfile.mkdtemp(prefix="vf-cdp-")
    process = subprocess.Popen(
        [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--window-size={width},{height}",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    socket_connection = None
    try:
        for _ in range(120):
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json/version", timeout=0.5
                ) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            raise OutputNotProducedError(
                "Chromium did not expose its debugging endpoint",
                details={"url": url},
            )
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as response:
            targets = json.loads(response.read().decode("utf-8"))
        page = next(
            (item for item in targets if item.get("type") == "page"),
            None,
        )
        if page is None or not page.get("webSocketDebuggerUrl"):
            raise OutputNotProducedError(
                "Chromium did not expose a page target",
                details={"url": url},
            )
        socket_connection = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=20)
        counter = 0

        def command(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            nonlocal counter
            counter += 1
            socket_connection.send(
                json.dumps({"id": counter, "method": method, "params": params or {}})
            )
            while True:
                message = json.loads(socket_connection.recv())
                if message.get("id") != counter:
                    continue
                if message.get("error"):
                    raise OutputNotProducedError(
                        f"Chromium CDP error: {message['error']}",
                        details={"method": method},
                    )
                return message.get("result") or {}

        command("Page.enable")
        command("Runtime.enable")
        command(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": int(width),
                "height": int(height),
                "deviceScaleFactor": 1.0,
                "mobile": False,
                "screenWidth": int(width),
                "screenHeight": int(height),
            },
        )
        command("Page.navigate", {"url": url})
        for _ in range(120):
            state = command(
                "Runtime.evaluate",
                {
                    "expression": "document.readyState",
                    "returnByValue": True,
                },
            )
            if (state.get("result") or {}).get("value") == "complete":
                break
            time.sleep(0.1)

        def clip_rect() -> dict[str, float] | None:
            if not clip_selector:
                return None
            expression = (
                "(() => { const e = document.querySelector("
                + json.dumps(clip_selector)
                + "); if (!e) return null;"
                " const r = e.getBoundingClientRect();"
                " return {x: r.x + window.scrollX, y: r.y + window.scrollY,"
                " width: r.width, height: r.height}; })()"
            )
            result = command(
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": True},
            )
            value = (result.get("result") or {}).get("value")
            return value if isinstance(value, dict) else None

        def capture(progress: float) -> bytes:
            ratio = max(0.0, min(1.0, float(progress)))
            if selector:
                script = (
                    f"const e = document.querySelector({json.dumps(selector)});"
                    "if (e) e.scrollIntoView({block: 'start', behavior: 'instant'});"
                )
            else:
                script = (
                    "window.scrollTo({top:"
                    "(document.documentElement.scrollHeight - window.innerHeight)"
                    f"*{ratio}, behavior:'instant'}});"
                )
            command("Runtime.evaluate", {"expression": script})
            time.sleep(0.05)
            params: dict[str, Any] = {"format": "png", "fromSurface": True}
            rect = clip_rect()
            if rect and rect.get("width") and rect.get("height"):
                params["clip"] = {
                    "x": max(0.0, float(rect["x"])),
                    "y": max(0.0, float(rect["y"])),
                    "width": float(rect["width"]),
                    "height": float(rect["height"]),
                    "scale": 1,
                }
            params["optimizeForSpeed"] = True
            result = command("Page.captureScreenshot", params)
            return base64.b64decode(result.get("data", ""))

        yield capture
    finally:
        if socket_connection is not None:
            with _contextlib.suppress(Exception):
                socket_connection.close()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile, ignore_errors=True)
