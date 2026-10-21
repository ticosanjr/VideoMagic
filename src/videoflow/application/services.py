"""Discover, stop, and report local VideoFlow service processes."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from videoflow.runtime import portable_home

PROC_ROOT = Path("/proc")


@dataclass(frozen=True, slots=True)
class ServiceProcess:
    pid: int
    cmdline: tuple[str, ...] = ()
    ports: tuple[int, ...] = ()
    version: str | None = None
    current: bool = False
    protected: bool = False

    @property
    def port(self) -> int | None:
        return self.ports[0] if self.ports else None

    @property
    def url(self) -> str | None:
        return f"http://127.0.0.1:{self.port}/" if self.port else None

    @property
    def kind(self) -> str:
        names = {Path(value).name.lower() for value in self.cmdline if value}
        if any(name.endswith(".appimage") for name in names):
            return "launcher"
        if self.ports:
            return "service"
        return "worker"

    def to_dict(self) -> dict[str, object]:
        return {
            "pid": self.pid,
            "kind": self.kind,
            "cmdline": list(self.cmdline),
            "ports": list(self.ports),
            "port": self.port,
            "version": self.version,
            "url": self.url,
            "current": self.current,
            "protected": self.protected,
        }


def pid_file() -> Path:
    return portable_home() / "server.pid"


def server_log_path() -> Path:
    return portable_home() / "logs" / "server.log"


def append_server_log(message: str) -> None:
    path = server_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 4_000_000:
            path.replace(path.with_suffix(".log.1"))
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {message.rstrip()}\n")
    except OSError:
        pass


def read_server_log(lines: int = 200) -> str:
    path = server_log_path()
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    limit = max(1, min(lines, 1000))
    return "\n".join(content[-limit:]) + ("\n" if content else "")


def write_pid_file(host: str, port: int) -> None:
    path = pid_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "host": host,
                "port": port,
                "url": f"http://{host if host not in {'0.0.0.0', '::'} else '127.0.0.1'}:{port}/",
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def read_pid_file() -> dict[str, Any]:
    try:
        payload = json.loads(pid_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if isinstance(payload, int):
        return {"pid": payload}
    return payload if isinstance(payload, dict) else {}


def remove_pid_file() -> None:
    with contextlib.suppress(OSError):
        pid_file().unlink()


def _process_state(pid: int, proc_root: Path = PROC_ROOT) -> str:
    try:
        stat = (proc_root / str(pid) / "stat").read_text(encoding="utf-8")
        return stat.rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return ""


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return _process_state(pid) != "Z"


def probe_service(host: str, port: int, *, timeout: float = 0.6) -> dict[str, Any] | None:
    visible = host if host not in {"0.0.0.0", "::"} else "127.0.0.1"
    try:
        with urllib.request.urlopen(
            f"http://{visible}:{port}/health", timeout=timeout
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    if isinstance(payload, dict) and payload.get("service") == "videoflow":
        return payload
    return None


def port_is_busy(host: str, port: int) -> bool:
    visible = host if host not in {"0.0.0.0", "::"} else "127.0.0.1"
    try:
        with socket.create_connection((visible, port), timeout=0.35):
            return True
    except OSError:
        return False


def _read_cmdline(pid: int, proc_root: Path = PROC_ROOT) -> tuple[str, ...]:
    try:
        raw = (proc_root / str(pid) / "cmdline").read_bytes()
    except OSError:
        return ()
    return tuple(
        part.decode("utf-8", "replace") for part in raw.split(b"\0") if part
    )


def _is_videoflow_command(parts: tuple[str, ...]) -> bool:
    names = {Path(value).name.lower() for value in parts if value}
    if not any(
        name in {"videoflow", "videoflow.exe"}
        or name.startswith("videoflow-")
        for name in names
    ):
        return False
    return any(value in {"serve", "mcp", "desktop"} for value in parts)


def _listening_inodes(proc_root: Path = PROC_ROOT) -> dict[str, int]:
    ports: dict[str, int] = {}
    for name in ("net/tcp", "net/tcp6"):
        try:
            lines = (proc_root / name).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines[1:]:
            fields = line.split()
            if len(fields) < 10 or fields[3] != "0A":
                continue
            try:
                port = int(fields[1].rsplit(":", 1)[1], 16)
            except (ValueError, IndexError):
                continue
            ports[fields[9]] = port
    return ports


def _process_ports(pid: int, ports_by_inode: dict[str, int], proc_root: Path) -> tuple[int, ...]:
    found: set[int] = set()
    try:
        entries = list((proc_root / str(pid) / "fd").iterdir())
    except OSError:
        return ()
    for entry in entries:
        try:
            target = os.readlink(entry)
        except OSError:
            continue
        if not target.startswith("socket:["):
            continue
        inode = target[8:-1]
        port = ports_by_inode.get(inode)
        if port is not None:
            found.add(port)
    return tuple(sorted(found))


def _ancestors(pid: int | None = None, proc_root: Path = PROC_ROOT) -> set[int]:
    current = pid or os.getpid()
    seen: set[int] = set()
    while current > 1 and current not in seen:
        seen.add(current)
        try:
            stat = (proc_root / str(current) / "stat").read_text(encoding="utf-8")
            fields = stat.rsplit(")", 1)[1].split()
            current = int(fields[1])
        except (OSError, ValueError, IndexError):
            break
    return seen


def discover_services(
    *,
    proc_root: Path = PROC_ROOT,
    current_pid: int | None = None,
) -> list[ServiceProcess]:
    """Return local VideoFlow serve processes, with their listening ports."""

    if not proc_root.is_dir():
        return []
    current = current_pid or os.getpid()
    protected = _ancestors(current, proc_root)
    appimage = os.environ.get("APPIMAGE", "")
    ports_by_inode = _listening_inodes(proc_root)
    services: list[ServiceProcess] = []
    try:
        candidates = [entry for entry in proc_root.iterdir() if entry.name.isdigit()]
    except OSError:
        return []
    for entry in candidates:
        try:
            pid = int(entry.name)
        except ValueError:
            continue
        if _process_state(pid, proc_root) == "Z":
            continue
        cmdline = _read_cmdline(pid, proc_root)
        if not cmdline or not _is_videoflow_command(cmdline):
            continue
        ports = _process_ports(pid, ports_by_inode, proc_root)
        version = None
        for port in ports:
            health = probe_service("127.0.0.1", port)
            if health is not None:
                version = str(health.get("version") or "") or None
                break
        current_launcher = bool(appimage) and any(
            value == appimage for value in cmdline
        )
        services.append(
            ServiceProcess(
                pid=pid,
                cmdline=cmdline,
                ports=ports,
                version=version,
                current=pid == current,
                protected=pid in protected or current_launcher,
            )
        )
    services.sort(key=lambda item: (not item.current, item.port or 0, item.pid))
    return services


def stop_service_pid(
    pid: int,
    *,
    proc_root: Path = PROC_ROOT,
    timeout: float = 3.0,
    allow_current: bool = False,
) -> bool:
    if pid <= 0:
        return False
    if not allow_current and (pid == os.getpid() or pid in _ancestors(os.getpid(), proc_root)):
        return False
    cmdline = _read_cmdline(pid, proc_root)
    if not cmdline or not _is_videoflow_command(cmdline):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    deadline = time.monotonic() + max(0.1, timeout)
    while time.monotonic() < deadline and process_alive(pid):
        time.sleep(0.1)
    if process_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            return False
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and process_alive(pid):
            time.sleep(0.05)
    return not process_alive(pid)


def stop_other_services(
    *,
    proc_root: Path = PROC_ROOT,
    current_pid: int | None = None,
) -> dict[str, object]:
    services = discover_services(proc_root=proc_root, current_pid=current_pid)
    stopped: list[int] = []
    failed: list[int] = []
    ordered = sorted(
        (item for item in services if not item.current and not item.protected),
        key=lambda item: (not bool(item.ports), item.pid),
    )
    for service in ordered:
        if stop_service_pid(service.pid, proc_root=proc_root):
            stopped.append(service.pid)
        else:
            failed.append(service.pid)
    return {"stopped": stopped, "failed": failed, "services": [item.to_dict() for item in services]}


def stop_services_on_port(
    host: str,
    port: int,
    *,
    proc_root: Path = PROC_ROOT,
    timeout: float = 5.0,
) -> dict[str, object]:
    services = [
        item
        for item in discover_services(proc_root=proc_root)
        if port in item.ports and not item.current
    ]
    targets = {item.pid for item in services}
    protected = _ancestors(os.getpid(), proc_root)
    for service in services:
        for ancestor in _ancestors(service.pid, proc_root):
            if ancestor in protected or ancestor == os.getpid():
                continue
            if ancestor in targets:
                continue
            if _is_videoflow_command(_read_cmdline(ancestor, proc_root)):
                targets.add(ancestor)
    port_pids = {item.pid for item in services if item.ports}
    stopped: list[int] = []
    failed: list[int] = []
    for pid in sorted(targets, key=lambda item: (0 if item in port_pids else 1, item)):
        if stop_service_pid(pid, proc_root=proc_root):
            stopped.append(pid)
        else:
            failed.append(pid)
    deadline = time.monotonic() + max(0.5, timeout)
    while time.monotonic() < deadline and port_is_busy(host, port):
        time.sleep(0.1)
    return {
        "stopped": stopped,
        "failed": failed,
        "free": not port_is_busy(host, port),
    }
