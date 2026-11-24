"""Dynamic server ports, active_server.json and Windows tray safety."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from types import SimpleNamespace

from videoflow.application import services
from videoflow.application.render_gate import RenderGate
from videoflow.application.services import (
    active_server_path,
    pick_available_port,
    read_active_server,
)


def _busy_socket(host: str = "127.0.0.1") -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((host, 0))
    sock.listen(1)
    return sock


def test_pick_available_port_skips_a_real_listener(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    occupied = _busy_socket()
    try:
        port = occupied.getsockname()[1]
        chosen = pick_available_port("127.0.0.1", port, span=20)
        assert chosen != port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", chosen))
    finally:
        occupied.close()


def test_pick_available_port_skips_a_port_that_accepts_connections(monkeypatch) -> None:
    """Windows may allow a second bind on a listening port; trust connect too."""

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def bind(self, address):
            return None

        def setsockopt(self, *args):
            return None

    monkeypatch.setattr(services.socket, "socket", lambda *args, **kwargs: FakeSocket())
    monkeypatch.setattr(services, "port_is_busy", lambda host, port: port == 8765)
    assert services.pick_available_port("127.0.0.1", 8765, span=5) == 8766


def test_server_supervisor_falls_back_and_publishes_active_port(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    from videoflow.application import tray

    occupied = _busy_socket()
    try:
        preferred = occupied.getsockname()[1]

        class FakeServer:
            should_exit = False

            def run(self) -> None:
                return None

        supervisor = tray.ServerSupervisor(
            "127.0.0.1",
            preferred,
            server_factory=lambda app, host, port, level: FakeServer(),
            app_factory=lambda: SimpleNamespace(state=SimpleNamespace()),
        )
        assert supervisor.start() is True
        try:
            assert supervisor.port != preferred
            payload = read_active_server()
            assert payload["port"] == supervisor.port
            assert payload["pid"] == os.getpid()
            assert active_server_path().is_file()
        finally:
            supervisor.stop()
    finally:
        occupied.close()
    assert read_active_server() == {}


def test_ancestor_pids_contains_the_parent() -> None:
    from videoflow.application.process_control import ancestor_pids

    ancestors = ancestor_pids(os.getpid())
    parent = os.getppid()
    if parent > 1:
        assert parent in ancestors


def test_windows_stop_protects_ancestors(monkeypatch) -> None:
    calls: list[tuple[int, bool]] = []
    monkeypatch.setattr(
        services, "os", SimpleNamespace(name="nt", getpid=lambda: 999_999)
    )
    monkeypatch.setattr(services, "ancestor_pids", lambda _pid: {4242})
    monkeypatch.setattr(services, "_windows_image_name", lambda _pid: "videoflow.exe")
    monkeypatch.setattr(
        services,
        "terminate_pid",
        lambda pid, *, force=False, timeout=0: calls.append((pid, force)) or True,
    )
    assert services.stop_service_pid(4242) is False
    assert calls == []


def test_render_gate_reports_real_cross_process_support(tmp_path: Path) -> None:
    status = RenderGate(path=tmp_path / "render.lock").status()
    assert status["cross_process"] is True


def test_tray_crash_report_is_written(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    from videoflow.application import tray

    try:
        raise RuntimeError("tray exploded")
    except RuntimeError as exc:
        path = tray._write_tray_crash(exc)
    assert path.is_file()
    assert "RuntimeError: tray exploded" in path.read_text(encoding="utf-8")


def test_active_server_payload_is_bom_safe(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    path = active_server_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"host": "127.0.0.1", "port": 9001}),
        encoding="utf-8-sig",
    )
    assert read_active_server()["port"] == 9001
