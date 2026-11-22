"""Deterministic Chromium frame capture driven by the Web Animations API."""

from __future__ import annotations

import contextlib
import json
import shutil
import tempfile
from typing import Any

from .browser import _chrome
from .errors import MissingCommandError, OutputNotProducedError


@contextlib.contextmanager
def _cdp_frame_capture(
    url: str,
    *,
    width: int,
    height: int,
    alpha: bool = False,
    scale: float = 1.0,
    jpeg: bool = False,
    timeout_sec: float = 10.0,
):
    """Reuse one Chromium target to capture animation frames deterministically.

    Frames are driven by seeking ``document.getAnimations()`` instead of
    starting a fresh browser per frame, so a 5 s card renders in seconds. Every
    CDP command has a hard timeout; a stalled page cannot hang the render.
    """

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
            "deterministic frame capture requires websocket-client",
            details={"env": ["VF_CHROME_BIN"], "capability": "motion"},
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
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            f"--window-size={width},{height}",
            "--force-device-scale-factor=1",
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
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/list", timeout=2
        ) as response:
            targets = json.loads(response.read().decode("utf-8"))
        page = next((item for item in targets if item.get("type") == "page"), None)
        if page is None or not page.get("webSocketDebuggerUrl"):
            raise OutputNotProducedError(
                "Chromium did not expose a page target", details={"url": url}
            )
        socket_connection = websocket.create_connection(
            page["webSocketDebuggerUrl"], timeout=timeout_sec
        )
        counter = 0

        def command(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            nonlocal counter
            counter += 1
            try:
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
            except OutputNotProducedError:
                raise
            except Exception as exc:  # noqa: BLE001 - timeouts and closed sockets
                raise OutputNotProducedError(
                    f"Chromium CDP {method} timed out after {timeout_sec:.1f}s",
                    details={"url": url},
                ) from exc

        command("Page.enable")
        command("Runtime.enable")
        command(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": int(width),
                "height": int(height),
                "deviceScaleFactor": max(0.1, float(scale)),
                "mobile": False,
                "screenWidth": int(width),
                "screenHeight": int(height),
            },
        )
        if alpha:
            command(
                "Emulation.setDefaultBackgroundColorOverride",
                {"color": {"r": 0, "g": 0, "b": 0, "a": 0}},
            )
        command("Page.navigate", {"url": url})
        for _ in range(100):
            state = command(
                "Runtime.evaluate",
                {"expression": "document.readyState", "returnByValue": True},
            )
            if (state.get("result") or {}).get("value") == "complete":
                break
            time.sleep(0.1)

        def capture(moment: float) -> bytes:
            milliseconds = max(0.0, float(moment)) * 1000.0
            expression = f"""(() => {{
  const t = {milliseconds:.3f};
  window.__vfTime = t / 1000;
  try {{
    for (const animation of document.getAnimations()) {{
      animation.pause();
      animation.currentTime = t;
    }}
  }} catch (error) {{}}
  window.dispatchEvent(new CustomEvent('vf-frame', {{detail: {{time: t / 1000}}}}));
  void document.documentElement.getBoundingClientRect();
  return true;
}})()"""
            command(
                "Runtime.evaluate",
                {
                    "expression": expression,
                    "returnByValue": True,
                },
            )
            result = command(
                "Page.captureScreenshot",
                {
                    "format": "jpeg" if jpeg else "png",
                    "quality": 88,
                    "fromSurface": True,
                    "captureBeyondViewport": False,
                    "optimizeForSpeed": True,
                },
            )
            payload = result.get("data", "")
            if not payload:
                raise OutputNotProducedError(
                    "Chromium returned an empty screenshot",
                    details={"time_sec": moment},
                )
            return base64.b64decode(payload)

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
