"""Tray icon that owns the local VideoFlow service.

``pystray`` runs on the main thread. The Uvicorn server runs on a daemon worker
thread, so stopping or restarting the service never rebuilds the tray process.
"""

from __future__ import annotations

import contextlib
import os
import signal
import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from typing import Any

from videoflow import __version__
from videoflow.application.services import (
    append_server_log,
    port_is_busy,
    probe_service,
    remove_pid_file,
    stop_services_on_port,
    write_pid_file,
)
from videoflow.domain.errors import VideoFlowError
from videoflow.runtime import bundle_root


class TrayError(VideoFlowError):
    """The tray could not start or control the local service."""

    code = "tray_failed"


def _uvicorn_server(app: Any, host: str, port: int, log_level: str) -> Any:
    import uvicorn

    return uvicorn.Server(
        uvicorn.Config(app, host=host, port=port, log_level=log_level)
    )


def _http_app() -> Any:
    from videoflow.api.app import create_http_app

    return create_http_app()


def _ui_url(host: str, port: int) -> str:
    visible = host if host not in {"0.0.0.0", "::"} else "127.0.0.1"
    return f"http://{visible}:{port}/"


def _browser_url(url: str) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}v={__version__}"


def _wait_for_service(host: str, port: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + max(0.1, timeout)
    while time.monotonic() < deadline:
        if probe_service(host, port) is not None:
            return True
        time.sleep(0.1)
    return False


class ServerSupervisor:
    """Own one Uvicorn server on a worker thread and map it to the PID file."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        server_factory: Callable[[Any, str, int, str], Any] | None = None,
        app_factory: Callable[[], Any] | None = None,
        log_level: str = "info",
    ) -> None:
        self.host = host
        self.port = port
        self._server_factory = server_factory or _uvicorn_server
        self._app_factory = app_factory or _http_app
        self._log_level = log_level
        self._server: Any | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._last_error = ""

    @property
    def url(self) -> str:
        return _ui_url(self.host, self.port)

    @property
    def running(self) -> bool:
        thread = self._thread
        return bool(thread is not None and thread.is_alive())

    @property
    def last_error(self) -> str:
        return self._last_error

    def start(self) -> bool:
        """Start the owned server. Returns False when it is already running."""

        with self._lock:
            if self.running:
                return False
            self._clear_port()
            app = self._app_factory()
            app.state.port = self.port
            app.state.host = self.host
            server = self._server_factory(app, self.host, self.port, self._log_level)
            thread = threading.Thread(
                target=self._run_server,
                args=(server,),
                name="videoflow-server",
                daemon=True,
            )
            write_pid_file(self.host, self.port)
            self._server = server
            self._thread = thread
            self._last_error = ""
            append_server_log(
                f"tray start host={self.host} port={self.port} pid={os.getpid()}"
            )
            try:
                thread.start()
            except Exception as exc:
                self._server = None
                self._thread = None
                remove_pid_file()
                raise TrayError(
                    f"Could not start the VideoFlow server thread: {exc}"
                ) from exc
            return True

    def stop(self, timeout: float = 5.0) -> bool:
        """Stop the owned server and remove the PID file."""

        with self._lock:
            server = self._server
            thread = self._thread
            self._server = None
            self._thread = None
        if server is None and thread is None:
            return False
        if server is not None:
            with contextlib.suppress(Exception):
                server.should_exit = True
        if thread is not None and thread.is_alive():
            thread.join(max(0.1, timeout))
            if thread.is_alive():
                self._last_error = "The server did not stop within the timeout."
                append_server_log(self._last_error)
        remove_pid_file()
        append_server_log(f"tray stop pid={os.getpid()}")
        return True

    def restart(self) -> bool:
        self.stop()
        return self.start()

    def _clear_port(self) -> None:
        health = probe_service(self.host, self.port)
        if health is None and not port_is_busy(self.host, self.port):
            return
        result = stop_services_on_port(self.host, self.port)
        if not bool(result.get("free")):
            raise TrayError(
                f"Port {self.port} is already in use and could not be freed."
            )
        append_server_log(f"tray replaced service on port {self.port}")

    def _run_server(self, server: Any) -> None:
        try:
            server.run()
        except Exception as exc:  # noqa: BLE001 - keep the tray alive
            self._last_error = str(exc)
            append_server_log(f"tray server error: {exc}")
        finally:
            with self._lock:
                current = self._server is server
            if current:
                remove_pid_file()
                append_server_log("tray server exited")


class TrayActions:
    """Menu behavior kept separate from the GUI toolkit for tests."""

    def __init__(
        self,
        supervisor: ServerSupervisor,
        *,
        opener: Callable[[str], Any] | None = None,
    ) -> None:
        self.supervisor = supervisor
        self._opener = opener or webbrowser.open

    def open_ui(self) -> None:
        if not self.supervisor.running:
            self.supervisor.start()
        self._opener(_browser_url(self.supervisor.url))

    def start(self) -> None:
        self.supervisor.start()

    def stop(self) -> None:
        self.supervisor.stop()

    def restart(self) -> None:
        self.supervisor.restart()

    def status_label(self) -> str:
        return "Status: running" if self.supervisor.running else "Status: stopped"


def tray_available() -> bool:
    """Return True when a tray backend and a display are both available."""

    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        return False
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
    except Exception:  # noqa: BLE001 - optional dependency
        return False
    return True


def _icon_image() -> Any:
    from PIL import Image, ImageDraw

    candidate = bundle_root() / "packaging" / "videoflow.png"
    if candidate.is_file():
        with Image.open(candidate) as source:
            return source.convert("RGBA").copy()
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 61, 61), radius=14, fill=(15, 23, 42, 255))
    draw.polygon([(24, 18), (50, 32), (24, 46)], fill=(56, 189, 248, 255))
    return image


def _run_action(icon: Any, action: Callable[[], Any]) -> None:
    try:
        action()
    except Exception as exc:  # noqa: BLE001 - a menu action must not kill the tray
        append_server_log(f"tray action failed: {exc}")
    finally:
        with contextlib.suppress(Exception):
            icon.update_menu()


def _menu(pystray: Any, actions: TrayActions, on_quit: Callable[[Any], None]) -> Any:
    Item = pystray.MenuItem
    supervisor = actions.supervisor
    return pystray.Menu(
        Item(
            "Open VideoFlow",
            lambda icon, _item: _run_action(icon, actions.open_ui),
            default=True,
        ),
        Item(
            "Start service",
            lambda icon, _item: _run_action(icon, actions.start),
            enabled=lambda _item: not supervisor.running,
        ),
        Item(
            "Stop service",
            lambda icon, _item: _run_action(icon, actions.stop),
            enabled=lambda _item: supervisor.running,
        ),
        Item(
            "Restart service",
            lambda icon, _item: _run_action(icon, actions.restart),
            enabled=lambda _item: supervisor.running,
        ),
        pystray.Menu.SEPARATOR,
        Item(lambda _item: actions.status_label(), None, enabled=False),
        pystray.Menu.SEPARATOR,
        Item("Quit", lambda icon, _item: on_quit(icon)),
    )


def _install_signal_handlers(icon: Any) -> None:
    def handler(_signum: int, _frame: Any) -> None:
        with contextlib.suppress(Exception):
            icon.stop()

    for name in ("SIGINT", "SIGTERM"):
        value = getattr(signal, name, None)
        if value is None:
            continue
        with contextlib.suppress(Exception):
            signal.signal(value, handler)


def run_tray(*, host: str, port: int, open_browser: bool = True) -> int:
    """Start the owned service and run the tray loop until Quit."""

    try:
        import pystray
    except Exception as exc:  # noqa: BLE001 - optional dependency
        print(f"VideoFlow tray backend is unavailable: {exc}", file=sys.stderr)
        return 1
    from videoflow.application.settings import load_settings

    supervisor = ServerSupervisor(
        host, port, log_level=load_settings().runtime.log_level
    )
    actions = TrayActions(supervisor)
    try:
        supervisor.start()
    except TrayError as exc:
        print(f"Could not start VideoFlow: {exc}", file=sys.stderr)
        return 1
    if open_browser:
        _wait_for_service(host, port)
        with contextlib.suppress(Exception):
            actions.open_ui()

    def on_quit(icon: Any) -> None:
        supervisor.stop()
        with contextlib.suppress(Exception):
            icon.stop()

    try:
        icon = pystray.Icon(
            "videoflow", _icon_image(), "VideoFlow", _menu(pystray, actions, on_quit)
        )
    except Exception as exc:  # noqa: BLE001 - missing desktop integration
        supervisor.stop()
        print(f"Could not create the VideoFlow tray icon: {exc}", file=sys.stderr)
        return 1
    _install_signal_handlers(icon)
    try:
        icon.run()
    except Exception as exc:  # noqa: BLE001 - backend failure after startup
        print(f"VideoFlow tray stopped: {exc}", file=sys.stderr)
        return 1
    finally:
        supervisor.stop()
    return 0


__all__ = [
    "ServerSupervisor",
    "TrayActions",
    "TrayError",
    "run_tray",
    "tray_available",
]
