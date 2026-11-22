"""Extra behavioral coverage for application-layer modules."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import numpy as np
import pytest

from videoflow.application import (
    database,
    model_downloads,
    models,
    service_definitions,
    services,
)
from videoflow.application import (
    settings as app_settings,
)
from videoflow.domain.errors import (
    CapabilityUnavailableError,
    FilesystemError,
    IngestError,
    JobCancelledError,
    StateNotReadyError,
)
from videoflow.domains.audio import analysis as audio_analysis
from videoflow.domains.media import assets

# --------------------------------------------------------------------------- services


def test_service_process_helpers() -> None:
    worker = services.ServiceProcess(pid=1, cmdline=("python", "worker.py"))
    assert worker.port is None
    assert worker.url is None
    assert worker.kind == "worker"
    service = services.ServiceProcess(pid=2, ports=(8765,))
    assert service.port == 8765
    assert service.url == "http://127.0.0.1:8765/"
    assert service.kind == "service"
    launcher = services.ServiceProcess(pid=3, cmdline=("/apps/VideoFlow.AppImage",))
    assert launcher.kind == "launcher"
    assert service.to_dict()["port"] == 8765


def test_videoflow_command_detection() -> None:
    assert services._is_videoflow_command(("videoflow.exe", "serve"))
    assert services._is_videoflow_command(("videoflow-api", "mcp"))
    assert not services._is_videoflow_command(("videoflow", "--help"))
    assert not services._is_videoflow_command(("python", "serve"))


def test_pid_file_and_server_log_roundtrip(monkeypatch, tmp_path: Path) -> None:
    services.write_pid_file("0.0.0.0", 8000)
    payload = services.read_pid_file()
    assert payload["pid"] == os.getpid()
    assert payload["host"] == "0.0.0.0"
    assert payload["url"] == "http://127.0.0.1:8000/"
    assert payload["started_at"]
    services.remove_pid_file()
    assert services.read_pid_file() == {}

    pid_path = services.pid_file()
    pid_path.write_text("123", encoding="utf-8")
    assert services.read_pid_file() == {"pid": 123}
    pid_path.write_text("[1, 2]", encoding="utf-8")
    assert services.read_pid_file() == {}
    pid_path.write_text("{bad", encoding="utf-8")
    assert services.read_pid_file() == {}

    services.append_server_log("hello world\n")
    log_path = services.server_log_path()
    content = log_path.read_text(encoding="utf-8")
    assert content.endswith("hello world\n")
    assert services.read_server_log(lines=1).endswith("hello world\n")
    assert services.read_server_log().strip().endswith("hello world")
    assert services.read_server_log(lines=0).endswith("hello world\n")
    assert services.server_log_path().name == "server.log"
    log_path.unlink()
    assert services.read_server_log() == ""

    blocked = tmp_path / "blocked"
    blocked.write_text("file", encoding="utf-8")
    monkeypatch.setattr(services, "server_log_path", lambda: blocked / "logs" / "server.log")
    services.append_server_log("ignored")


def test_rotate_server_log_branches(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "server.log"
    assert services.rotate_log(log_path) is False
    log_path.write_bytes(b"x" * 10)
    assert services.rotate_log(log_path, max_bytes=100) is False
    assert services.rotate_log(log_path, max_bytes=4, keep=2) is True
    assert (tmp_path / "server.log.1").is_file()
    log_path.write_bytes(b"y" * 10)
    assert services.rotate_log(log_path, max_bytes=4, keep=2) is True
    assert (tmp_path / "server.log.2").is_file()

    class _BadPath:
        def exists(self) -> bool:
            raise OSError("stat failed")

    assert services.rotate_log(_BadPath()) is False  # type: ignore[arg-type]


def test_process_state_alive_and_cmdline(monkeypatch, tmp_path: Path) -> None:
    proc = tmp_path / "42"
    proc.mkdir()
    (proc / "stat").write_text("42 (videoflow) Z 1 1", encoding="utf-8")
    assert services._process_state(42, tmp_path) == "Z"
    (proc / "stat").write_text("garbage", encoding="utf-8")
    assert services._process_state(42, tmp_path) == ""
    assert services._process_state(999, tmp_path) == ""

    assert services.process_alive(0) is False
    monkeypatch.setattr(
        services.os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError())
    )
    assert services.process_alive(5) is False
    monkeypatch.setattr(
        services.os, "kill", lambda pid, sig: (_ for _ in ()).throw(PermissionError())
    )
    assert services.process_alive(5) is True
    monkeypatch.setattr(services.os, "kill", lambda pid, sig: None)
    monkeypatch.setattr(services, "_process_state", lambda pid: "Z")
    assert services.process_alive(5) is False
    monkeypatch.setattr(services, "_process_state", lambda pid: "S")
    assert services.process_alive(5) is True

    (proc / "cmdline").write_bytes(b"/usr/bin/videoflow\0serve\0--open\0")
    assert services._read_cmdline(42, tmp_path) == (
        "/usr/bin/videoflow",
        "serve",
        "--open",
    )
    assert services._read_cmdline(999, tmp_path) == ()


def test_listening_inodes_and_process_ports(monkeypatch, tmp_path: Path) -> None:
    net = tmp_path / "net"
    net.mkdir()
    header = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when inode\n"
    rows = [
        "   0: 0100007F:1F90 00000000:0000 0A 00000000:00000000 00:00000000 "
        "00000000 1000 0 12345 1 0 0 10 0",
        "   1: 0100007F:1F91 00000000:0000 01 00000000:00000000 00:00000000 "
        "00000000 1000 0 22222 1 0 0 10 0",
        "   2: 0100007F:ZZZZ 00000000:0000 0A 00000000:00000000 00:00000000 "
        "00000000 1000 0 33333 1 0 0 10 0",
        "   3: short",
    ]
    (net / "tcp").write_text(header + "\n".join(rows) + "\n", encoding="utf-8")
    assert services._listening_inodes(tmp_path) == {"12345": 8080}

    proc = tmp_path / "7"
    (proc / "fd").mkdir(parents=True)
    (proc / "fd" / "3").symlink_to("socket:[12345]")
    (proc / "fd" / "4").symlink_to("pipe:[1]")
    (proc / "fd" / "5").mkdir()
    (proc / "fd" / "6").symlink_to("socket:[999]")
    assert services._process_ports(7, {"12345": 8080}, tmp_path) == (8080,)
    assert services._process_ports(999, {"12345": 8080}, tmp_path) == ()


def test_probe_service_and_port_is_busy(monkeypatch) -> None:
    class _Response:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            return False

        def read(self) -> bytes:
            return self.payload

    monkeypatch.setattr(
        services.urllib.request,
        "urlopen",
        lambda url, timeout: _Response(b'{"service": "videoflow", "version": "1.0"}'),
    )
    assert services.probe_service("0.0.0.0", 8000)["version"] == "1.0"

    monkeypatch.setattr(
        services.urllib.request,
        "urlopen",
        lambda url, timeout: _Response(b'{"service": "other"}'),
    )
    assert services.probe_service("127.0.0.1", 8000) is None

    monkeypatch.setattr(
        services.urllib.request, "urlopen", lambda url, timeout: _Response(b"not json")
    )
    assert services.probe_service("127.0.0.1", 8000) is None

    def broken(url, timeout):
        raise OSError("refused")

    monkeypatch.setattr(services.urllib.request, "urlopen", broken)
    assert services.probe_service("127.0.0.1", 8000) is None

    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            return False

    monkeypatch.setattr(
        services.socket, "create_connection", lambda address, timeout: _Connection()
    )
    assert services.port_is_busy("0.0.0.0", 8000) is True

    def refused(address, timeout):
        raise OSError("refused")

    monkeypatch.setattr(services.socket, "create_connection", refused)
    assert services.port_is_busy("127.0.0.1", 8000) is False


def test_ancestors_walk_and_break(tmp_path: Path) -> None:
    first = tmp_path / "5"
    second = tmp_path / "3"
    first.mkdir()
    second.mkdir()
    (first / "stat").write_text("5 (videoflow) S 3 1 1", encoding="utf-8")
    (second / "stat").write_text("3 (init) S 1 1 1", encoding="utf-8")
    assert services._ancestors(5, tmp_path) == {5, 3}
    (first / "stat").write_text("5 (videoflow) S 99 1 1", encoding="utf-8")
    assert services._ancestors(5, tmp_path) == {5, 99}


def _write_proc(root: Path, pid: int, cmdline: bytes, state: str = "S") -> None:
    process = root / str(pid)
    (process / "fd").mkdir(parents=True)
    (process / "cmdline").write_bytes(cmdline)
    (process / "stat").write_text(f"{pid} (videoflow) {state} 1 1\n", encoding="utf-8")


def test_discover_services_filters_and_flags(monkeypatch, tmp_path: Path) -> None:
    header = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when inode\n"
    row = (
        "   0: 0100007F:223D 00000000:0000 0A 00000000:00000000 00:00000000 "
        "00000000 1000 0 11111 1 0 0 10 0\n"
        "   1: 0100007F:2328 00000000:0000 0A 00000000:00000000 00:00000000 "
        "00000000 1000 0 22222 1 0 0 10 0\n"
        "   2: 0100007F:223E 00000000:0000 0A 00000000:00000000 00:00000000 "
        "00000000 1000 0 33333 1 0 0 10 0\n"
    )
    (tmp_path / "net").mkdir()
    (tmp_path / "net" / "tcp").write_text(header + row, encoding="utf-8")
    _write_proc(tmp_path, 12, b"/opt/videoflow\0serve\0--open\0")
    (tmp_path / "12" / "fd" / "3").symlink_to("socket:[11111]")
    (tmp_path / "12" / "fd" / "4").symlink_to("socket:[22222]")
    _write_proc(tmp_path, 16, b"/opt/videoflow\0serve\0")
    (tmp_path / "16" / "fd" / "3").symlink_to("socket:[33333]")
    _write_proc(tmp_path, 13, b"/opt/videoflow\0serve\0", state="Z")
    _write_proc(tmp_path, 14, b"/usr/bin/python\0serve\0")
    (tmp_path / "15").mkdir()
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    (tmp_path / "\u00b2").write_text("x", encoding="utf-8")

    def fake_probe(host, port):
        return None if port in {8765, 8766} else {"version": "9.9"}

    monkeypatch.setattr(services, "probe_service", fake_probe)

    found = services.discover_services(proc_root=tmp_path, current_pid=999)
    assert [item.pid for item in found] == [12, 16]
    assert found[0].ports == (8765, 9000)
    assert found[0].version == "9.9"
    assert found[1].version is None
    assert found[0].protected is False

    current = services.discover_services(proc_root=tmp_path, current_pid=12)
    assert current[0].current is True

    monkeypatch.setenv("APPIMAGE", "/opt/videoflow")
    protected = services.discover_services(proc_root=tmp_path, current_pid=999)
    assert protected[0].protected is True

    assert services.discover_services(proc_root=tmp_path / "absent") == []


def test_discover_services_tolerates_unreadable_proc(monkeypatch) -> None:
    class _FakeProc:
        def is_dir(self) -> bool:
            return True

        def __truediv__(self, name: str):
            return self

        def read_text(self, *args, **kwargs):
            raise OSError("denied")

        def iterdir(self):
            raise OSError("denied")

    assert services.discover_services(proc_root=_FakeProc(), current_pid=1) == []


def test_stop_service_pid_guards_and_signals(monkeypatch) -> None:
    monkeypatch.setattr(services, "_ancestors", lambda *a, **k: set())
    assert services.stop_service_pid(0) is False
    assert services.stop_service_pid(-5) is False
    monkeypatch.setattr(services, "_ancestors", lambda *a, **k: {77})
    assert services.stop_service_pid(77) is False
    monkeypatch.setattr(services, "_ancestors", lambda *a, **k: set())

    monkeypatch.setattr(services, "_read_cmdline", lambda pid, root: ())
    assert services.stop_service_pid(88) is False
    monkeypatch.setattr(
        services, "_read_cmdline", lambda pid, root: ("/usr/bin/python", "serve")
    )
    assert services.stop_service_pid(88) is False

    monkeypatch.setattr(
        services, "_read_cmdline", lambda pid, root: ("/usr/bin/videoflow", "serve")
    )
    monkeypatch.setattr(services, "_is_videoflow_command", lambda parts: True)

    def missing(pid, sig):
        raise ProcessLookupError()

    monkeypatch.setattr(services.os, "kill", missing)
    assert services.stop_service_pid(88) is True

    def denied(pid, sig):
        raise OSError("denied")

    monkeypatch.setattr(services.os, "kill", denied)
    assert services.stop_service_pid(88) is False

    kills: list[int] = []
    monkeypatch.setattr(services.os, "kill", lambda pid, sig: kills.append(sig))
    monkeypatch.setattr(services, "process_alive", lambda pid: False)
    assert services.stop_service_pid(88, timeout=0) is True
    assert kills == [signal.SIGTERM]

    kills.clear()
    alive = iter([True, False, True, True, False, False])
    monkeypatch.setattr(services, "process_alive", lambda pid: next(alive))
    monkeypatch.setattr(services.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(services.time, "sleep", lambda seconds: None)
    assert services.stop_service_pid(88, timeout=0) is True
    assert kills == [signal.SIGTERM, signal.SIGKILL]

    kills.clear()

    def kill_then_fail(pid, sig):
        kills.append(sig)
        if sig == signal.SIGKILL:
            raise OSError("cannot kill")

    alive = iter([True, False, True])
    monkeypatch.setattr(services, "process_alive", lambda pid: next(alive))
    monkeypatch.setattr(services.os, "kill", kill_then_fail)
    assert services.stop_service_pid(88, timeout=0) is False


def test_stop_other_services_orders_by_port(monkeypatch) -> None:
    processes = [
        services.ServiceProcess(pid=2, ports=(9000,)),
        services.ServiceProcess(pid=1),
        services.ServiceProcess(pid=3, ports=(8000,), current=True),
        services.ServiceProcess(pid=4, ports=(8001,), protected=True),
    ]
    monkeypatch.setattr(services, "discover_services", lambda **kwargs: processes)
    stopped_pids: list[int] = []

    def fake_stop(pid, **kwargs):
        stopped_pids.append(pid)
        return pid != 1

    monkeypatch.setattr(services, "stop_service_pid", fake_stop)
    result = services.stop_other_services()
    assert stopped_pids == [2, 1]
    assert result["stopped"] == [2]
    assert result["failed"] == [1]
    assert len(result["services"]) == 4


def test_stop_services_on_port_collects_ancestors(monkeypatch) -> None:
    processes = [
        services.ServiceProcess(pid=10, ports=(8765,)),
        services.ServiceProcess(pid=11, ports=(8765,)),
        services.ServiceProcess(pid=12, ports=(9000,)),
        services.ServiceProcess(pid=13, ports=(8765,), current=True),
    ]
    monkeypatch.setattr(services, "discover_services", lambda **kwargs: processes)

    def fake_ancestors(pid=None, root=None):
        if pid == os.getpid():
            return {os.getpid()}
        if pid == 10:
            return {10, os.getpid(), 60, 61}
        return {pid, 60, 61}

    monkeypatch.setattr(services, "_ancestors", fake_ancestors)

    def fake_cmdline(pid, root):
        if pid == 61:
            return ("/usr/bin/python", "serve")
        return ("/usr/bin/videoflow", "serve")

    monkeypatch.setattr(services, "_read_cmdline", fake_cmdline)
    monkeypatch.setattr(
        services, "_is_videoflow_command", lambda parts: parts[0].endswith("videoflow")
    )
    busy = iter([True, False, False])
    monkeypatch.setattr(services, "port_is_busy", lambda host, port: next(busy))
    monkeypatch.setattr(services.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(services.time, "sleep", lambda seconds: None)
    stopped_pids: list[int] = []

    def fake_stop(pid, **kwargs):
        stopped_pids.append(pid)
        return pid != 11

    monkeypatch.setattr(services, "stop_service_pid", fake_stop)
    result = services.stop_services_on_port("127.0.0.1", 8765, timeout=0)
    assert stopped_pids == [10, 11, 60]
    assert result["stopped"] == [10, 60]
    assert result["failed"] == [11]
    assert result["free"] is True


# --------------------------------------------------------------------------- service definitions


class _FakeProcess:
    def __init__(self, pid: int = 4242, code: int | None = None) -> None:
        self.pid = pid
        self.code = code
        self.terminated = False
        self.killed = False
        self.waits = 0

    def poll(self) -> int | None:
        return self.code

    def wait(self, timeout: float | None = None) -> int | None:
        self.waits += 1
        return self.code

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


def _definition(**overrides):
    payload = {
        "id": "svc",
        "name": "Service",
        "command": "echo",
        "args": ["hello"],
        "port": 9000,
    }
    payload.update(overrides)
    return service_definitions.ServiceDefinition(**payload)


def test_definition_crud_and_export(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(service_definitions, "_RUNNING", {})
    service_definitions.save_definition(_definition())
    service_definitions.save_definition(_definition(id="other", name="Other"))
    assert {item.id for item in service_definitions.list_definitions()} == {"svc", "other"}
    exported = json.loads(service_definitions.export_definitions())
    assert {item["id"] for item in exported["services"]} == {"svc", "other"}
    service_definitions.delete_definition("svc")
    assert [item.id for item in service_definitions.load_definitions()] == ["other"]
    with pytest.raises(StateNotReadyError, match="Unknown service"):
        service_definitions.delete_definition("missing")

    with service_definitions._connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO service_definitions (id, payload, updated_at) "
            "VALUES (?, ?, ?)",
            ("broken", "{nope", "2000-01-01T00:00:00+00:00"),
        )
        connection.commit()
    assert [item.id for item in service_definitions.load_definitions()] == ["other"]


def test_rotate_service_log_and_read_logs(tmp_path: Path) -> None:
    log_path = tmp_path / "svc.log"
    assert service_definitions.rotate_service_log(log_path) is False
    log_path.write_bytes(b"x" * 10)
    assert service_definitions.rotate_service_log(log_path, max_bytes=100) is False
    assert service_definitions.rotate_service_log(log_path, max_bytes=4) is True
    assert (tmp_path / "svc.log.1").is_file()
    log_path.write_bytes(b"y" * 10)
    assert service_definitions.rotate_service_log(log_path, max_bytes=4, keep=2) is True
    assert (tmp_path / "svc.log.2").is_file()

    assert service_definitions.read_logs("missing") == ""
    logs_dir = service_definitions._logs_dir()
    assert logs_dir.is_dir()
    (logs_dir / "svc.log").write_text("one\ntwo\nthree\n", encoding="utf-8")
    assert service_definitions.read_logs("svc", lines=2) == "two\nthree"
    assert service_definitions.read_logs("svc", lines=0) == "three"


def test_resolve_command_and_health(monkeypatch, tmp_path: Path) -> None:
    script = tmp_path / "svc.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    assert service_definitions._resolve_command(str(script)) == str(script)
    monkeypatch.setattr(service_definitions.shutil, "which", lambda name: None)
    with pytest.raises(StateNotReadyError, match="not found"):
        service_definitions._resolve_command("definitely-not-a-command")
    monkeypatch.setattr(
        service_definitions.shutil, "which", lambda name: "/usr/bin/found"
    )
    assert service_definitions._resolve_command("found") == "/usr/bin/found"

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            return False

        def get(self, url: str):
            if url == "boom":
                raise httpx.HTTPError("broken")
            return SimpleNamespace(status_code=200 if url == "ok" else 500)

    monkeypatch.setattr(service_definitions.httpx, "Client", _Client)
    assert service_definitions._health("") is None
    assert service_definitions._health("ok") is True
    assert service_definitions._health("down") is False
    assert service_definitions._health("boom") is False


def test_start_status_and_stop_service(monkeypatch, tmp_path: Path) -> None:
    running: dict[str, object] = {}
    monkeypatch.setattr(service_definitions, "_RUNNING", running)
    script = tmp_path / "svc.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    service_definitions.save_definition(
        _definition(command=str(script), cwd=str(tmp_path), env={"EXTRA": "1"})
    )
    created: list[_FakeProcess] = []

    def fake_popen(args, **kwargs):
        process = _FakeProcess()
        process.args = args
        process.kwargs = kwargs
        created.append(process)
        return process

    monkeypatch.setattr(
        service_definitions,
        "subprocess",
        SimpleNamespace(
            Popen=fake_popen,
            STDOUT=subprocess.STDOUT,
            TimeoutExpired=subprocess.TimeoutExpired,
        ),
    )
    status = service_definitions.start_service("svc")
    assert status["status"] == "running"
    assert status["pid"] == 4242
    assert created[0].args == [str(script), "hello"]
    assert created[0].kwargs["cwd"] == str(tmp_path)
    assert created[0].kwargs["env"]["EXTRA"] == "1"
    assert service_definitions.start_service("svc")["pid"] == 4242
    assert len(created) == 1

    monkeypatch.setattr(
        service_definitions,
        "os",
        SimpleNamespace(
            environ=os.environ,
            getpgid=lambda pid: pid,
            killpg=lambda pgid, sig: None,
        ),
    )
    stopped = service_definitions.stop_service("svc")
    assert stopped == {"id": "svc", "status": "stopped", "pid": None}
    assert service_definitions.stop_service("svc")["status"] == "stopped"

    with pytest.raises(StateNotReadyError, match="Unknown service"):
        service_definitions.start_service("missing")
    service_definitions.save_definition(_definition(id="off", enabled=False))
    with pytest.raises(StateNotReadyError, match="disabled"):
        service_definitions.start_service("off")


def test_start_service_popen_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(service_definitions, "_RUNNING", {})
    script = tmp_path / "svc.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    service_definitions.save_definition(_definition(command=str(script)))

    def failing_popen(args, **kwargs):
        raise OSError("cannot spawn")

    monkeypatch.setattr(
        service_definitions,
        "subprocess",
        SimpleNamespace(
            Popen=failing_popen,
            STDOUT=subprocess.STDOUT,
            TimeoutExpired=subprocess.TimeoutExpired,
        ),
    )
    with pytest.raises(StateNotReadyError, match="Could not start"):
        service_definitions.start_service("svc")


def test_stop_service_timeout_escalates(monkeypatch) -> None:
    running: dict[str, object] = {}
    monkeypatch.setattr(service_definitions, "_RUNNING", running)

    class _SlowProcess(_FakeProcess):
        def wait(self, timeout: float | None = None) -> int | None:
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("svc", timeout)
            return 0

    process = _SlowProcess()
    running["svc"] = service_definitions.RunningService(
        definition=_definition(), process=process
    )

    def failing_killpg(pgid, sig):
        raise OSError("no group")

    monkeypatch.setattr(
        service_definitions,
        "os",
        SimpleNamespace(
            environ=os.environ,
            getpgid=lambda pid: pid,
            killpg=failing_killpg,
        ),
    )
    monkeypatch.setattr(
        service_definitions,
        "subprocess",
        SimpleNamespace(
            Popen=lambda *a, **k: process,
            STDOUT=subprocess.STDOUT,
            TimeoutExpired=subprocess.TimeoutExpired,
        ),
    )
    result = service_definitions.stop_service("svc")
    assert result["status"] == "stopped"
    assert process.terminated is True
    assert process.killed is True
    assert running == {}


def test_stop_service_already_exited(monkeypatch) -> None:
    running: dict[str, object] = {}
    monkeypatch.setattr(service_definitions, "_RUNNING", running)
    process = _FakeProcess(code=3)
    running["svc"] = service_definitions.RunningService(
        definition=_definition(), process=process
    )
    result = service_definitions.stop_service("svc")
    assert result == {"id": "svc", "status": "stopped", "pid": None}
    assert process.waits == 0
    assert running == {}


def test_status_service_variants(monkeypatch) -> None:
    running: dict[str, object] = {}
    monkeypatch.setattr(service_definitions, "_RUNNING", running)
    definition = _definition(health_url="http://127.0.0.1:9000/health")
    service_definitions.save_definition(definition)
    stopped = service_definitions.status_service("svc")
    assert stopped["status"] == "stopped"
    assert stopped["healthy"] is None

    monkeypatch.setattr(service_definitions, "_health", lambda url: True)
    process = _FakeProcess()
    running["svc"] = service_definitions.RunningService(
        definition=definition, process=process
    )
    status = service_definitions.status_service("svc")
    assert status["status"] == "running"
    assert status["healthy"] is True
    assert status["last_error"] == ""

    running["svc"].last_error = "boom"  # type: ignore[attr-defined]
    assert service_definitions.status_service("svc")["last_error"] == "boom"

    exited = _FakeProcess(code=3)
    running["svc"] = service_definitions.RunningService(
        definition=definition, process=exited
    )
    status = service_definitions.status_service("svc")
    assert status["status"] == "exited"
    assert status["pid"] is None
    assert status["last_error"] == "exit 3"
    assert status["healthy"] is None

    with pytest.raises(StateNotReadyError, match="Unknown service"):
        service_definitions.status_service("missing")
    assert service_definitions.list_statuses()[0]["id"] == "svc"


def test_autostart_and_stop_all(monkeypatch, tmp_path: Path) -> None:
    running: dict[str, object] = {}
    monkeypatch.setattr(service_definitions, "_RUNNING", running)
    script = tmp_path / "svc.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    service_definitions.save_definition(
        _definition(id="auto", command=str(script), autostart=True)
    )
    service_definitions.save_definition(
        _definition(id="disabled", command=str(script), autostart=True, enabled=False)
    )
    service_definitions.save_definition(
        _definition(id="broken", command="not-a-real-command-xyz", autostart=True)
    )
    monkeypatch.setattr(
        service_definitions,
        "subprocess",
        SimpleNamespace(
            Popen=lambda args, **kwargs: _FakeProcess(),
            STDOUT=subprocess.STDOUT,
            TimeoutExpired=subprocess.TimeoutExpired,
        ),
    )
    monkeypatch.setattr(
        service_definitions,
        "os",
        SimpleNamespace(
            environ=os.environ,
            getpgid=lambda pid: pid,
            killpg=lambda pgid, sig: None,
        ),
    )
    results = service_definitions.autostart()
    assert [item["id"] for item in results] == ["auto"]
    assert set(running) == {"auto"}
    service_definitions.stop_all()
    assert running == {}


# --------------------------------------------------------------------------- models


def test_local_model_registration_and_verify(monkeypatch, tmp_path: Path) -> None:
    weights = tmp_path / "weights.bin"
    weights.write_bytes(b"x" * 1500)
    with pytest.raises(StateNotReadyError, match="does not exist"):
        models.register_local_model(
            model_id="custom", label="x", capability="asr", path=str(tmp_path / "no")
        )
    with pytest.raises(StateNotReadyError, match="empty"):
        models.register_local_model(
            model_id="   ", label="x", capability="asr", path=str(weights)
        )

    entry = models.register_local_model(
        model_id="custom-asr", label="", capability="", path=str(weights), license="MIT"
    )
    assert entry["label"] == "custom-asr"
    assert entry["capability"] == "other"
    assert entry["size_mb"] == 0
    assert entry["used_by"] == ["local"]

    directory_entry = models.register_local_model(
        model_id="custom-dir", label="Dir", capability="asr", path=str(tmp_path)
    )
    assert directory_entry["size_mb"] == 0

    listed = {item["id"]: item for item in models.list_models()}
    assert listed["custom-asr"]["custom"] is True
    assert listed["custom-asr"]["installed"] is True
    assert listed["whisper-tiny"]["custom"] is False

    assert models.verify_model("custom-asr")["ok"] is True
    weights.unlink()
    assert models.verify_model("custom-asr")["ok"] is False

    models.remove_local_model("custom-dir")
    with pytest.raises(StateNotReadyError, match="Unknown local model"):
        models.remove_local_model("custom-dir")
    assert models.installed_path("custom-dir") is None

    local_file = Path(os.environ["VIDEOWFLOW_HOME"]) / models.LOCAL_FILE
    local_file.write_text("{invalid", encoding="utf-8")
    assert models._local_models() == {}


def test_verify_catalog_models(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "models"
    monkeypatch.setattr(models, "models_dir", lambda: root)
    whisper = root / "faster-whisper" / "small"
    whisper.mkdir(parents=True)
    for name in ("config.json", "tokenizer.json", "vocabulary.txt", "model.bin"):
        (whisper / name).write_bytes(b"data")
    result = models.verify_model("faster-whisper-small")
    assert result["ok"] is False
    assert result["invalid"] == ["model.bin"]
    assert len(result["files"]) == 4
    assert result["files"][0]["checksum_ok"] is None
    assert result["files"][3]["checksum_ok"] is False

    pyannote = root / "pyannote" / "speaker-diarization-3.1"
    pyannote.mkdir(parents=True)
    (pyannote / "config.yaml").write_text("pipeline: x\n", encoding="utf-8")
    assert models.verify_model("pyannote-diarization-3.1")["ok"] is True
    (pyannote / "config.yaml").unlink()
    assert models.verify_model("pyannote-diarization-3.1")["ok"] is False

    tiny = root / "whisper" / "ggml-base.bin"
    tiny.parent.mkdir(parents=True)
    tiny.write_bytes(b"data")
    assert models.verify_model("whisper-base")["ok"] is True
    assert models.installed_path("whisper-base") == tiny
    assert models.installed_path("unknown-model") is None


def test_models_dir_configuration(monkeypatch, tmp_path: Path) -> None:
    external = tmp_path / "external"
    monkeypatch.setenv("VIDEOWFLOW_EXTERNAL_HOME", str(external))
    default = models.models_dir()
    assert default == external / "models"
    assert default.is_dir()

    custom = tmp_path / "custom-models"
    monkeypatch.setattr(
        app_settings,
        "load_settings",
        lambda: SimpleNamespace(paths=SimpleNamespace(models_dir=str(custom))),
    )
    assert models.models_dir() == custom

    def broken():
        raise RuntimeError("settings failed")

    monkeypatch.setattr(app_settings, "load_settings", broken)
    assert models.models_dir() == external / "models"


class _Stream:
    def __init__(self, chunks: list[bytes], status: int = 200, headers: dict | None = None):
        self.chunks = chunks
        self.status_code = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        return False

    def iter_bytes(self):
        yield from self.chunks


def test_install_model_already_installed_and_network_guard(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "models"
    monkeypatch.setattr(models, "models_dir", lambda: root)
    target = root / "whisper" / "ggml-base.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"data")
    progress: list[tuple[int, str]] = []
    result = models.install_model("whisper-base", progress=lambda p, m: progress.append((p, m)))
    assert result["installed"] is True
    assert progress == [(100, "Already installed")]

    with pytest.raises(StateNotReadyError, match="Unknown model"):
        models.install_model("missing-model")
    with pytest.raises(CapabilityUnavailableError):
        models.install_model("faster-whisper-tiny", allow_network=False)


def test_install_model_downloads_resumes_and_fails(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "models"
    monkeypatch.setattr(models, "models_dir", lambda: root)
    target = root / "faster-whisper" / "tiny"
    target.mkdir(parents=True)
    (target / "tokenizer.json.part").write_bytes(b"old-")
    (target / "vocabulary.txt.part").write_bytes(b"stale")
    seen_headers: dict[str, dict] = {}

    def fake_stream(method, url, **kwargs):
        name = url.rsplit("/", 1)[-1]
        seen_headers[name] = kwargs.get("headers", {})
        if name == "tokenizer.json":
            return _Stream([b"new"], status=206, headers={"content-length": "3"})
        if name == "vocabulary.txt":
            return _Stream([b"fresh"], status=200, headers={"content-length": "5"})
        if name == "config.json":
            return _Stream([b"data"], status=200, headers={})
        return _Stream([b"data"], status=200, headers={"content-length": "4"})

    monkeypatch.setattr(models, "httpx", SimpleNamespace(stream=fake_stream))
    progress: list[tuple[int, str]] = []
    result = models.install_model(
        "faster-whisper-tiny", progress=lambda p, m: progress.append((p, m))
    )
    assert result["installed"] is True
    assert result["path"] == str(target)
    assert (target / "tokenizer.json").read_bytes() == b"old-new"
    assert (target / "vocabulary.txt").read_bytes() == b"fresh"
    assert (target / "model.bin").is_file()
    assert seen_headers["tokenizer.json"] == {"Range": "bytes=4-"}
    assert seen_headers["config.json"] == {}
    assert progress[-1] == (100, "Installed")
    assert any(message == "Downloading config.json" for _, message in progress)

    def http_error(method, url, **kwargs):
        return _Stream([], status=404, headers={})

    monkeypatch.setattr(models, "httpx", SimpleNamespace(stream=http_error))
    with pytest.raises(FilesystemError, match="HTTP 404"):
        models.install_model("whisper-base")

    tiny_target = root / "whisper" / "ggml-tiny.bin"

    def bad_checksum(method, url, **kwargs):
        return _Stream([b"not the model"], status=200, headers={"content-length": "12"})

    monkeypatch.setattr(models, "httpx", SimpleNamespace(stream=bad_checksum))
    with pytest.raises(FilesystemError, match="Checksum mismatch"):
        models.install_model("whisper-tiny")
    assert tiny_target.with_suffix(".bin.part").exists() is False

    with pytest.raises(JobCancelledError):
        models.install_model("whisper-small", should_cancel=lambda: True)


def test_install_model_cancel_mid_stream(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "models"
    monkeypatch.setattr(models, "models_dir", lambda: root)
    monkeypatch.setattr(
        models,
        "httpx",
        SimpleNamespace(
            stream=lambda *args, **kwargs: _Stream(
                [b"chunk"], status=200, headers={"content-length": "5"}
            )
        ),
    )
    checks = iter([False, True])
    with pytest.raises(JobCancelledError):
        models.install_model("whisper-base", should_cancel=lambda: next(checks))


def test_install_pyannote_model_paths(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "models"
    monkeypatch.setattr(models, "models_dir", lambda: root)
    with pytest.raises(FilesystemError, match="requires network"):
        models.install_model("pyannote-diarization-3.1", allow_network=False)

    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    with pytest.raises(FilesystemError, match="huggingface_hub"):
        models.install_model("pyannote-diarization-3.1")

    def snapshot_download(*, repo_id, local_dir, token):
        destination = Path(local_dir)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "config.yaml").write_text("pipeline: x\n", encoding="utf-8")

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=snapshot_download),
    )
    monkeypatch.delenv("HF_TOKEN", raising=False)
    progress: list[tuple[int, str]] = []
    result = models.install_model(
        "pyannote-diarization-3.1", progress=lambda p, m: progress.append((p, m))
    )
    assert result["installed"] is True
    assert (Path(str(result["path"])) / "config.yaml").is_file()
    assert progress[0][0] == 5
    assert progress[-1] == (100, "Installed")


def test_remove_model_variants(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "models"
    monkeypatch.setattr(models, "models_dir", lambda: root)
    with pytest.raises(StateNotReadyError, match="Unknown model"):
        models.remove_model("missing-model")

    local = tmp_path / "local.bin"
    local.write_bytes(b"x")
    models.register_local_model(
        model_id="local-one", label="Local", capability="asr", path=str(local)
    )
    models.remove_model("local-one")
    assert models.installed_path("local-one") is None

    target = root / "whisper" / "ggml-base.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"data")
    part = target.with_suffix(".bin.part")
    part.write_bytes(b"partial")
    models.remove_model("whisper-base")
    assert not target.exists()
    assert not part.exists()

    with pytest.raises(StateNotReadyError, match="not installed"):
        models.remove_model("whisper-base")

    directory = root / "faster-whisper" / "tiny"
    directory.mkdir(parents=True)
    (directory / "model.bin").write_bytes(b"x")
    models.remove_model("faster-whisper-tiny")
    assert not directory.exists()


# --------------------------------------------------------------------------- model downloads


class _ImmediateThread:
    def __init__(self, *, target, args=(), name=None, daemon=None) -> None:
        self.target = target
        self.args = args
        self.name = name
        self.daemon = daemon

    def start(self) -> None:
        self.target(*self.args)


def _fake_install(model_id, *, progress=None, should_cancel=None, **kwargs):
    if progress is not None:
        progress(42, "Half way")
    if should_cancel is not None:
        assert should_cancel() is False
    return {"installed": True}


def test_download_manager_success_and_persistence(monkeypatch) -> None:
    monkeypatch.setattr(model_downloads, "install_model", _fake_install)
    monkeypatch.setattr(model_downloads.threading, "Thread", _ImmediateThread)
    manager = model_downloads.ModelDownloadManager()
    item = manager.start("whisper-tiny")
    assert item.status == "installed"
    assert item.percent == 100
    assert item.message == "Installed"
    assert item.finished_at
    assert manager.get("whisper-tiny") is item
    listed = manager.list()
    assert listed[0]["model_id"] == "whisper-tiny"
    assert listed[0]["installed"] is False
    payload = json.loads(manager.path.read_text(encoding="utf-8"))
    assert payload["items"][0]["status"] == "installed"


def test_download_manager_failure_and_cancel(monkeypatch) -> None:
    manager = model_downloads.ModelDownloadManager()

    def boom(*args, **kwargs):
        raise RuntimeError("download exploded")

    monkeypatch.setattr(model_downloads, "install_model", boom)
    monkeypatch.setattr(model_downloads.threading, "Thread", _ImmediateThread)
    failed = manager.start("whisper-small")
    assert failed.status == "failed"
    assert failed.error == "download exploded"
    assert failed.message == "Download failed"

    def cancelled_install(model_id, **kwargs):
        manager.cancel(model_id)
        assert kwargs["should_cancel"]() is True
        raise JobCancelledError("Model download cancelled")

    monkeypatch.setattr(model_downloads, "install_model", cancelled_install)
    cancelled = manager.start("whisper-base")
    assert cancelled.status == "cancelled"
    assert cancelled.message == "Cancelled"
    assert cancelled.cancel_requested is True

    assert manager.cancel("unknown") is None
    queued = model_downloads.ModelDownload(model_id="queued", status="queued")
    manager._items["queued"] = queued
    assert manager.cancel("queued") is queued
    assert queued.cancel_requested is True
    done = model_downloads.ModelDownload(model_id="done", status="installed")
    manager._items["done"] = done
    assert manager.cancel("done") is done
    assert done.cancel_requested is False


def test_download_manager_skips_active_and_bad_state(monkeypatch) -> None:
    created: list[_ImmediateThread] = []

    class _CountingThread(_ImmediateThread):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            created.append(self)

    monkeypatch.setattr(model_downloads.threading, "Thread", _CountingThread)
    manager = model_downloads.ModelDownloadManager()
    active = model_downloads.ModelDownload(model_id="active", status="downloading")
    manager._items["active"] = active
    assert manager.start("active") is active
    assert created == []

    path = manager.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "items": [
                    {"model_id": "queued", "status": "queued", "percent": 5},
                    {"model_id": "running", "status": "downloading"},
                    {"model_id": "finished", "status": "installed", "percent": 100},
                    {"percent": 10},
                    {"model_id": "bad", "percent": "many"},
                ]
            }
        ),
        encoding="utf-8",
    )
    loaded = model_downloads.ModelDownloadManager()
    items = {item.model_id: item for item in loaded._items.values()}
    assert items["queued"].status == "interrupted"
    assert items["queued"].message == "Interrupted by restart"
    assert items["running"].status == "interrupted"
    assert items["finished"].status == "installed"
    assert set(items) == {"queued", "running", "finished"}

    path.write_text("{not json", encoding="utf-8")
    assert model_downloads.ModelDownloadManager().list() == []


# --------------------------------------------------------------------------- audio analysis


def test_energy_peaks_edge_cases() -> None:
    assert audio_analysis.energy_peaks(np.zeros(10, dtype=np.int16), 0) == []
    assert audio_analysis.energy_peaks(np.array([], dtype=np.int16), 1000) == []
    assert audio_analysis.energy_peaks(np.ones(50, dtype=np.int16), 1000) == []

    silent = np.zeros(1000, dtype=np.int16)
    assert audio_analysis.energy_peaks(silent, 1000) == []

    two_windows = np.concatenate(
        [np.zeros(100, dtype=np.int16), np.full(100, 1000, dtype=np.int16)]
    )
    assert audio_analysis.energy_peaks(two_windows, 1000, window_ms=100) == []

    quiet_then_loud = np.concatenate(
        [np.zeros(80 * 100, dtype=np.int16), np.full(20 * 100, 1000, dtype=np.int16)]
    )
    peaks = audio_analysis.energy_peaks(quiet_then_loud, 1000)
    assert peaks and peaks[0][0] == 8000
    assert peaks[-1][1] == 100 * 100

    two_bursts = np.zeros(10000, dtype=np.int16)
    two_bursts[5000:5010] = 1000
    two_bursts[5200:5210] = 1000
    merged = audio_analysis.energy_peaks(two_bursts, 1000, window_ms=100, min_gap_ms=200)
    assert len(merged) == 1
    assert merged[0][1] == 5300


def test_detect_audio_energy_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(audio_analysis, "find_binary", lambda name: None)
    with pytest.raises(IngestError, match="not available"):
        audio_analysis.detect_audio_energy(tmp_path / "a.wav", 16000)

    monkeypatch.setattr(audio_analysis, "find_binary", lambda name: "/usr/bin/ffmpeg")
    pcm = np.full(16000, 1000, dtype=np.int16).tobytes()
    monkeypatch.setattr(
        audio_analysis.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=pcm),
    )
    peaks = audio_analysis.detect_audio_energy(tmp_path / "a.wav", 32000)
    assert peaks
    assert peaks[0][0] % 2 == 0

    monkeypatch.setattr(
        audio_analysis.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout=b""),
    )
    with pytest.raises(IngestError, match="produced no PCM"):
        audio_analysis.detect_audio_energy(tmp_path / "a.wav", 16000)

    def broken_run(*args, **kwargs):
        raise OSError("ffmpeg failed")

    monkeypatch.setattr(audio_analysis.subprocess, "run", broken_run)
    with pytest.raises(IngestError, match="Audio analysis failed"):
        audio_analysis.detect_audio_energy(tmp_path / "a.wav", 16000)


def test_detect_beats_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(audio_analysis, "find_binary", lambda name: None)
    with pytest.raises(IngestError, match="not available"):
        audio_analysis.detect_beats(tmp_path / "a.wav")

    monkeypatch.setattr(audio_analysis, "find_binary", lambda name: "/usr/bin/ffmpeg")
    silent = np.zeros(16000, dtype=np.int16).tobytes()
    monkeypatch.setattr(
        audio_analysis.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=silent),
    )
    assert audio_analysis.detect_beats(tmp_path / "a.wav") == []

    samples = np.zeros(16000, dtype=np.int16)
    for start in range(0, 16000, 4000):
        samples[start : start + 200] = 20000
    monkeypatch.setattr(
        audio_analysis.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=samples.tobytes()),
    )
    beats = audio_analysis.detect_beats(tmp_path / "a.wav")
    assert beats
    assert all(value >= 0 for value in beats)

    blocks = [
        0, 0, 0, 5000, 9000, 0, 5000, 9000, 2000, 12000,
        500, 9000, 0, 9000, 5000, 2000, 0, 9000, 500, 500,
        5000, 500, 0, 5000, 0, 500, 2000, 0, 500, 0,
        5000, 500, 5000, 500, 9000, 9000, 0, 9000, 2000, 9000,
    ]
    envelope = np.repeat(np.array(blocks, dtype=np.int16), 320)
    monkeypatch.setattr(
        audio_analysis.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=envelope.tobytes()),
    )
    mixed = audio_analysis.detect_beats(tmp_path / "a.wav")
    assert len(mixed) >= 2

    monkeypatch.setattr(
        audio_analysis.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout=b""),
    )
    with pytest.raises(IngestError, match="produced no PCM"):
        audio_analysis.detect_beats(tmp_path / "a.wav")

    def broken_run(*args, **kwargs):
        raise OSError("ffmpeg failed")

    monkeypatch.setattr(audio_analysis.subprocess, "run", broken_run)
    with pytest.raises(IngestError, match="Beat detection failed"):
        audio_analysis.detect_beats(tmp_path / "a.wav")


# --------------------------------------------------------------------------- assets


def test_asset_scan_kinds_hidden_and_skips(tmp_path: Path) -> None:
    root = tmp_path / "media"
    nested = root / "nested"
    hidden = root / ".cache"
    nested.mkdir(parents=True)
    hidden.mkdir(parents=True)
    files = {
        "clip.mp4": b"v",
        "track.MP3": b"a",
        "photo.png": b"i",
        "font.ttf": b"f",
        "notes.txt": b"t",
        ".hidden.mp4": b"h",
    }
    for name, content in files.items():
        (root / name).write_bytes(content)
    (nested / "deep.mov").write_bytes(b"m")
    (hidden / "secret.mp4").write_bytes(b"s")

    records = assets.scan_directory(root)
    names = {item["name"] for item in records}
    assert names == {"clip.mp4", "track.MP3", "photo.png", "font.ttf", "deep.mov"}
    assert {item["name"] for item in assets.list_assets()} == names
    kinds = {item["name"]: item["kind"] for item in records}
    assert kinds["clip.mp4"] == "video"
    assert kinds["track.MP3"] == "audio"
    assert kinds["photo.png"] == "image"
    assert kinds["font.ttf"] == "font"
    assert assets.index_path().is_file()

    flat = assets.scan_directory(root, recursive=False, tags=["Hero", " hero ", ""])
    assert {item["name"] for item in flat} == {
        "clip.mp4",
        "track.MP3",
        "photo.png",
        "font.ttf",
    }
    assert flat[0]["tags"] == ["Hero", "hero"]

    assert assets.scan_directory(tmp_path / "absent") == []
    empty = tmp_path / "empty"
    empty.mkdir()
    assert assets.scan_directory(empty) == []
    assert assets._kind(".xyz") == "other"
    assert assets._kind(".WAV") == "audio"


def test_asset_scan_tolerates_record_and_database_failures(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "media"
    root.mkdir()
    (root / "bad.mp4").write_bytes(b"x")
    (root / "good.mp4").write_bytes(b"y")
    original = assets._record

    def flaky(path, tags=None):
        if path.name == "bad.mp4":
            raise OSError("vanished")
        return original(path, tags)

    monkeypatch.setattr(assets, "_record", flaky)

    def broken_upsert(asset_id, payload):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(database, "upsert_asset", broken_upsert)
    records = assets.scan_directory(root)
    assert [item["name"] for item in records] == ["good.mp4"]
    payload = json.loads(assets.index_path().read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert [item["name"] for item in payload["assets"]] == ["good.mp4"]


def _seed_index(records: list[dict]) -> None:
    index = assets.index_path()
    index.write_text(json.dumps({"ok": True, "assets": records}), encoding="utf-8")


def test_asset_index_fallback_search_and_pagination(monkeypatch, tmp_path: Path) -> None:
    def broken_db(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(database, "list_assets_db", broken_db)
    records = [
        {
            "id": "a",
            "name": "Alpha.mp4",
            "path": "/media/Alpha.mp4",
            "kind": "video",
            "tags": ["hero"],
            "added_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": "b",
            "name": "Beta.mp3",
            "path": "/media/Beta.mp3",
            "kind": "audio",
            "tags": ["music"],
            "added_at": "2026-02-01T00:00:00+00:00",
        },
        {
            "id": "c",
            "name": "Gamma.png",
            "path": "/media/Gamma.png",
            "kind": "image",
            "tags": ["hero"],
            "added_at": "2026-03-01T00:00:00+00:00",
        },
    ]
    _seed_index(records)
    assert [item["id"] for item in assets.list_assets()] == ["c", "b", "a"]
    assert [item["id"] for item in assets.list_assets(kind="video")] == ["a"]
    assert [item["id"] for item in assets.list_assets(query="HERO")] == ["c", "a"]
    assert [item["id"] for item in assets.list_assets(query="music")] == ["b"]
    assert [item["id"] for item in assets.list_assets(query="gamma.png")] == ["c"]
    assert assets.list_assets(limit=1, offset=1)[0]["id"] == "b"
    assert len(assets.list_assets(limit=0, offset=-5)) == 1

    assert assets.get_asset("b")["name"] == "Beta.mp3"
    assert assets.get_asset("missing") is None
    updated = assets.update_tags("b", [" z ", "", "a", "z"])
    assert updated is not None and updated["tags"] == ["a", "z"]
    assert assets.update_tags("missing", ["x"]) is None
    assert assets.remove_asset("a") is True
    assert assets.remove_asset("a") is False
    assert [item["id"] for item in assets.list_assets()] == ["c", "b"]


def test_asset_index_payload_variants(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(database, "list_assets_db", lambda *a, **k: [])
    index = assets.index_path()
    index.write_text("{bad", encoding="utf-8")
    assert assets.list_assets() == []
    index.write_text("[]", encoding="utf-8")
    assert assets.list_assets() == []
    index.write_text(json.dumps({"assets": [{"id": "ok"}, "skip"]}), encoding="utf-8")
    assert assets.list_assets() == [{"id": "ok"}]
