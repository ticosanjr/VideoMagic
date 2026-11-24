"""Tray icon that owns the local VideoFlow service.

``pystray`` runs on the main thread. The Uvicorn server runs on a daemon worker
thread, so stopping or restarting the service never rebuilds the tray process.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from videoflow import __version__
from videoflow.application.services import (
    append_server_log,
    pick_available_port,
    port_is_busy,
    probe_service,
    remove_active_server,
    remove_pid_file,
    stop_services_on_port,
    write_active_server,
    write_pid_file,
)
from videoflow.domain.errors import VideoFlowError
from videoflow.runtime import bundle_root, portable_home


class TrayError(VideoFlowError):
    """The tray could not start or control the local service."""

    code = "tray_failed"


def _uvicorn_server(app: Any, host: str, port: int, log_level: str) -> Any:
    import uvicorn

    return uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level=log_level))


def _http_app() -> Any:
    from videoflow.api.app import create_http_app

    return create_http_app()


def _ui_url(host: str, port: int) -> str:
    visible = host if host not in {"0.0.0.0", "::"} else "127.0.0.1"
    return f"http://{visible}:{port}/"


def _open_url(url: str) -> None:
    """Open a URL, falling back to the desktop opener used by AppImages."""

    try:
        if webbrowser.open(url):
            return
    except Exception:  # noqa: BLE001 - browser discovery is best effort
        pass
    for command in (["xdg-open", url], ["gio", "open", url]):
        if shutil.which(command[0]) is None:
            continue
        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return
        except OSError:
            continue
    append_server_log(f"could not open browser for {url}")


def _browser_url(url: str, fragment: str = "") -> str:
    separator = "&" if "?" in url else "?"
    base = f"{url}{separator}v={__version__}"
    return f"{base}#{fragment}" if fragment else base


def _wait_for_service(host: str, port: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + max(0.1, timeout)
    while time.monotonic() < deadline:
        if probe_service(host, port) is not None:
            return True
        time.sleep(0.1)
    return False


class TrayJobController:
    """Read and control job execution through the local HTTP API."""

    def __init__(self, base_url: str, *, timeout: float = 4.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(method, f"{self.base_url}{path}", json=payload)
            response.raise_for_status()
            data = response.json()
        return data if isinstance(data, dict) else {}

    def snapshot(self) -> dict[str, int]:
        payload = self._request("GET", "/api/v1/jobs?summary=true&limit=100")
        jobs = payload.get("jobs")
        counts = {
            "running": 0,
            "queued": 0,
            "paused": 0,
            "waiting": 0,
            "total": 0,
        }
        for job in jobs if isinstance(jobs, list) else []:
            if not isinstance(job, dict):
                continue
            counts["total"] += 1
            status = str(job.get("status") or "")
            if status in {"running", "rendering"}:
                counts["running"] += 1
            elif status == "queued":
                counts["queued"] += 1
            elif status == "paused":
                counts["paused"] += 1
            elif status in {"waiting_approval", "waiting_input"}:
                counts["waiting"] += 1
        return counts

    def pause_all(self) -> dict[str, Any]:
        return self._request("POST", "/api/v1/jobs/pause_all")

    def resume_all(self) -> dict[str, Any]:
        return self._request("POST", "/api/v1/jobs/resume_all")

    def cancel_all(self) -> dict[str, Any]:
        return self._request("POST", "/api/v1/jobs/cancel_all?force=true")


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
            write_active_server(self.host, self.port)
            self._server = server
            self._thread = thread
            self._last_error = ""
            append_server_log(f"tray start host={self.host} port={self.port} pid={os.getpid()}")
            try:
                thread.start()
            except Exception as exc:
                self._server = None
                self._thread = None
                remove_pid_file()
                remove_active_server()
                raise TrayError(f"Could not start the VideoFlow server thread: {exc}") from exc
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
                with contextlib.suppress(Exception):
                    server.force_exit = True
                thread.join(1.0)
            if thread.is_alive():
                self._last_error = "The server did not stop within the timeout."
                append_server_log(self._last_error)
        remove_pid_file()
        remove_active_server()
        append_server_log(f"tray stop pid={os.getpid()}")
        return True

    def restart(self) -> bool:
        self.stop()
        return self.start()

    def _clear_port(self) -> None:
        health = probe_service(self.host, self.port)
        busy = port_is_busy(self.host, self.port)
        start = self.port
        if health is not None:
            result = stop_services_on_port(self.host, self.port)
            if bool(result.get("free")):
                append_server_log(f"tray replaced service on port {self.port}")
            else:
                # A real listener is still holding the port; skip it explicitly.
                start = self.port + 1
        elif not busy:
            append_server_log(f"tray checking port {self.port}")
        previous = self.port
        try:
            self.port = pick_available_port(self.host, start, span=100)
        except OSError as exc:
            raise TrayError(f"Port {previous} is busy and no fallback was found: {exc}") from exc
        if self.port != previous:
            append_server_log(
                f"tray port {previous} is owned by another process; using {self.port}"
            )

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
        jobs: TrayJobController | None = None,
    ) -> None:
        self.supervisor = supervisor
        self._opener = opener or _open_url
        self.jobs = jobs or TrayJobController(getattr(supervisor, "url", ""))
        self.job_stats: dict[str, int] = {
            "running": 0,
            "queued": 0,
            "paused": 0,
            "waiting": 0,
            "total": 0,
        }
        self.job_error = ""
        self.unreachable = False

    def _wait_ready(self) -> None:
        host = getattr(self.supervisor, "host", "")
        port = getattr(self.supervisor, "port", 0)
        if host and port:
            _wait_for_service(str(host), int(port))
        self.jobs.base_url = self.supervisor.url.rstrip("/")

    def open_ui(self) -> None:
        if not self.supervisor.running:
            self.supervisor.start()
        self._wait_ready()
        self.unreachable = False
        self._opener(_browser_url(self.supervisor.url))

    def open_runs(self) -> None:
        if not self.supervisor.running:
            self.supervisor.start()
        self._wait_ready()
        self.unreachable = False
        self._opener(_browser_url(self.supervisor.url, "runs"))

    def refresh_status(self) -> None:
        if not bool(getattr(self.supervisor, "running", False)):
            self.unreachable = False
            return
        host = getattr(self.supervisor, "host", "127.0.0.1")
        port = getattr(self.supervisor, "port", 8765)
        try:
            self.unreachable = probe_service(host, port) is None
        except Exception:  # noqa: BLE001 - the menu must stay responsive
            self.unreachable = True

    def refresh_jobs(self) -> None:
        try:
            self.job_stats = self.jobs.snapshot()
            self.job_error = ""
        except Exception as exc:  # noqa: BLE001 - the tray must stay responsive
            self.job_error = str(exc)

    def jobs_label(self) -> str:
        if self.job_error and not any(self.job_stats.values()):
            return "Jobs: unavailable"
        parts: list[str] = []
        if self.job_stats.get("running"):
            parts.append(f"{self.job_stats['running']} running")
        if self.job_stats.get("queued"):
            parts.append(f"{self.job_stats['queued']} queued")
        if self.job_stats.get("paused"):
            parts.append(f"{self.job_stats['paused']} paused")
        if self.job_stats.get("waiting"):
            parts.append(f"{self.job_stats['waiting']} waiting")
        return "Jobs: " + (" · ".join(parts) if parts else "idle")

    def pause_jobs(self) -> None:
        self.jobs.pause_all()
        self.refresh_jobs()

    def resume_jobs(self) -> None:
        self.jobs.resume_all()
        self.refresh_jobs()

    def cancel_jobs(self) -> None:
        self.jobs.cancel_all()
        self.refresh_jobs()

    def start(self) -> None:
        self.supervisor.start()
        self._wait_ready()
        self.unreachable = False

    def stop(self) -> None:
        self.supervisor.stop()
        self.unreachable = False

    def restart(self) -> None:
        self.supervisor.restart()
        self._wait_ready()
        self.unreachable = False

    def status_label(self) -> str:
        if not bool(getattr(self.supervisor, "running", False)):
            return "Service: stopped"
        if self.unreachable:
            return "Service: unreachable"
        return "Service: running"


@contextlib.contextmanager
def _system_gi_path():
    """Temporarily expose Debian/Ubuntu's system PyGObject.

    The whole dist-packages directory must not stay on ``sys.path``: it can
    shadow newer virtualenv/bundle packages (for example ``websockets`` and
    break Uvicorn). Import pystray inside this context so its backend and gi
    bindings load, then restore the path.
    """

    candidate = "/usr/lib/python3/dist-packages"
    added = False
    if sys.platform.startswith("linux") and os.path.isdir(candidate) and candidate not in sys.path:
        sys.path.append(candidate)
        added = True
    try:
        yield
    finally:
        if added:
            with contextlib.suppress(ValueError):
                sys.path.remove(candidate)


def _import_pystray() -> Any:
    """Import pystray, preferring a backend that supports a menu.

    AppIndicator and GTK expose menus; the xorg backend only runs a default
    action. System PyGObject usually lives outside the virtualenv or frozen
    bundle, so expose it only while pystray selects and loads its backend.
    ``VIDEOWFLOW_TRAY_BACKEND`` can force ``appindicator``, ``gtk``, or ``xorg``.
    """

    requested = os.environ.get("VIDEOWFLOW_TRAY_BACKEND", "").strip()
    if requested:
        os.environ["PYSTRAY_BACKEND"] = requested
    try:
        with _system_gi_path():
            import pystray
    finally:
        if requested:
            os.environ.pop("PYSTRAY_BACKEND", None)
    return pystray


def _gi_error() -> str:
    if not sys.platform.startswith("linux"):
        return ""
    try:
        with _system_gi_path():
            import gi

            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk  # noqa: F401
        return ""
    except Exception as exc:  # noqa: BLE001 - optional system integration
        return f"{type(exc).__name__}: {exc}"


def _gi_status() -> tuple[bool, bool]:
    """Return ``(gi_available, appindicator_available)``."""

    if not sys.platform.startswith("linux"):
        return True, True
    try:
        with _system_gi_path():
            import gi

            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk  # noqa: F401

            try:
                gi.require_version("AyatanaAppIndicator3", "0.1")
                from gi.repository import AyatanaAppIndicator3  # noqa: F401
            except (ImportError, ValueError):
                return True, False
            return True, True
    except Exception:  # noqa: BLE001 - optional system integration
        return False, False


def tray_diagnostics() -> dict[str, Any]:
    """Describe the tray backend, display, and menu availability."""

    display = os.environ.get("DISPLAY", "") or os.environ.get("WAYLAND_DISPLAY", "")
    payload: dict[str, Any] = {
        "available": False,
        "platform": sys.platform,
        "display": display,
        "backend": "",
        "has_menu": False,
        "gi": False,
        "appindicator": False,
        "gi_error": _gi_error(),
        "reason": "",
    }
    if sys.platform.startswith("linux") and not display:
        payload["reason"] = "no DISPLAY or WAYLAND_DISPLAY"
        return payload
    try:
        pystray = _import_pystray()
        from PIL import Image  # noqa: F401
    except Exception as exc:  # noqa: BLE001 - optional dependency
        payload["reason"] = f"tray dependencies are unavailable: {exc}"
        return payload
    backend = str(getattr(pystray.Icon, "__module__", ""))
    has_menu = bool(getattr(pystray.Icon, "HAS_MENU", True))
    gi_available, appindicator = _gi_status()
    payload.update(
        {
            "backend": backend,
            "has_menu": has_menu,
            "gi": gi_available,
            "appindicator": appindicator,
        }
    )
    if not pystray.Icon or backend.endswith("._dummy"):
        payload["reason"] = "no usable pystray backend"
        return payload
    if not has_menu:
        payload["reason"] = (
            f"{backend} has no menu; install python3-gi and gir1.2-ayatanaappindicator3-0.1"
        )
        return payload
    payload["available"] = True
    return payload


def tray_available() -> bool:
    """Return True when a menu-capable tray backend and a display are available."""

    return bool(tray_diagnostics()["available"])


def _write_tray_crash(exc: BaseException) -> Path:
    directory = portable_home() / "crash-reports"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"tray-{int(time.time())}.log"
    detail = traceback.format_exc()
    if detail.strip() == "NoneType: None":
        detail = f"{type(exc).__name__}: {exc}"
    path.write_text(detail, encoding="utf-8")
    append_server_log(f"tray crash report: {path}")
    return path


def _icon_image() -> Any:
    from PIL import Image, ImageDraw

    candidates = [
        bundle_root() / "packaging" / "videoflow.png",
        Path(__file__).resolve().parents[2] / "packaging" / "videoflow.png",
    ]
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.insert(0, Path(meipass) / "packaging" / "videoflow.png")
    for candidate in candidates:
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
        Item(f"VideoFlow {__version__}", None, enabled=False),
        Item(lambda _item: actions.status_label(), None, enabled=False),
        Item(lambda _item: actions.jobs_label(), None, enabled=False),
        pystray.Menu.SEPARATOR,
        Item(
            "Open VideoFlow",
            lambda icon, _item: _run_action(icon, actions.open_ui),
        ),
        Item(
            "Open runs",
            lambda icon, _item: _run_action(icon, actions.open_runs),
        ),
        pystray.Menu.SEPARATOR,
        Item(
            "Restart service",
            lambda icon, _item: _run_action(icon, actions.restart),
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
        pystray.Menu.SEPARATOR,
        Item(
            "Pause all jobs",
            lambda icon, _item: _run_action(icon, actions.pause_jobs),
            enabled=lambda _item: bool(
                actions.job_stats.get("running") or actions.job_stats.get("queued")
            ),
        ),
        Item(
            "Resume all jobs",
            lambda icon, _item: _run_action(icon, actions.resume_jobs),
            enabled=lambda _item: bool(actions.job_stats.get("paused")),
        ),
        Item(
            "Cancel all jobs",
            lambda icon, _item: _run_action(icon, actions.cancel_jobs),
            enabled=lambda _item: bool(
                actions.job_stats.get("running")
                or actions.job_stats.get("queued")
                or actions.job_stats.get("paused")
                or actions.job_stats.get("waiting")
            ),
        ),
        pystray.Menu.SEPARATOR,
        Item("Quit VideoFlow", lambda icon, _item: on_quit(icon)),
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
        pystray = _import_pystray()
    except Exception as exc:  # noqa: BLE001 - optional dependency
        _write_tray_crash(exc)
        print(f"VideoFlow tray backend is unavailable: {exc}", file=sys.stderr)
        return 1
    append_server_log(f"tray backend={getattr(pystray.Icon, '__module__', 'unknown')}")
    if not getattr(pystray.Icon, "HAS_MENU", True):
        append_server_log(
            "tray menu unavailable: install python3-gi and gir1.2-ayatanaappindicator3-0.1"
        )
    from videoflow.application.settings import load_settings

    supervisor = ServerSupervisor(host, port, log_level=load_settings().runtime.log_level)
    actions = TrayActions(supervisor)
    stop_poller = threading.Event()

    try:
        supervisor.start()
    except TrayError as exc:
        print(f"Could not start VideoFlow: {exc}", file=sys.stderr)
        return 1
    actions.jobs.base_url = str(getattr(supervisor, "url", "")).rstrip("/")
    if open_browser:
        _wait_for_service(host, int(getattr(supervisor, "port", port)))
        with contextlib.suppress(Exception):
            actions.open_ui()

    def on_quit(icon: Any) -> None:
        stop_poller.set()
        supervisor.stop()
        with contextlib.suppress(Exception):
            icon.stop()

    try:
        icon = pystray.Icon(
            "videoflow", _icon_image(), "VideoFlow", _menu(pystray, actions, on_quit)
        )
    except Exception as exc:  # noqa: BLE001 - missing desktop integration
        _write_tray_crash(exc)
        stop_poller.set()
        supervisor.stop()
        print(f"Could not create the VideoFlow tray icon: {exc}", file=sys.stderr)
        return 1

    def poll_status() -> None:
        while not stop_poller.is_set():
            actions.refresh_status()
            actions.refresh_jobs()
            with contextlib.suppress(Exception):
                icon.update_menu()
            stop_poller.wait(5.0)

    threading.Thread(target=poll_status, name="videoflow-tray-jobs", daemon=True).start()
    _install_signal_handlers(icon)
    try:
        icon.run()
    except Exception as exc:  # noqa: BLE001 - backend failure after startup
        _write_tray_crash(exc)
        print(f"VideoFlow tray stopped: {exc}", file=sys.stderr)
        return 1
    finally:
        stop_poller.set()
        supervisor.stop()
    return 0


__all__ = [
    "ServerSupervisor",
    "TrayActions",
    "TrayError",
    "run_tray",
    "tray_available",
]
