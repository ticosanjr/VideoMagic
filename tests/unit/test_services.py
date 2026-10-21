"""Local service discovery and cleanup helpers."""

from __future__ import annotations

import os
from pathlib import Path

from videoflow.application import services


def make_proc(root: Path, pid: int, port: int, cmdline: bytes) -> None:
    process = root / str(pid)
    (process / "fd").mkdir(parents=True)
    (process / "cmdline").write_bytes(cmdline)
    (process / "stat").write_text(f"{pid} (videoflow) S 1 1 1 0 -1 0 0 0 0 0 0\n", encoding="utf-8")
    inode = "999"
    (process / "fd" / "3").symlink_to(f"socket:[{inode}]")
    (root / "net").mkdir(exist_ok=True)
    header = (
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when "
        "retrnsmt   uid  timeout inode\n"
    )
    row = (
        f"   0: 0100007F:{port:04X} 00000000:0000 0A 00000000:00000000 "
        f"00:00000000 00000000 1000 0 {inode} 1 0 0 10 0\n"
    )
    (root / "net" / "tcp").write_text(header + row, encoding="utf-8")


def test_discovers_a_videoflow_service_by_port(monkeypatch, tmp_path: Path) -> None:
    make_proc(
        tmp_path,
        123,
        8765,
        b"/tmp/.mount/usr/bin/videoflow\0serve\0--open\0",
    )
    monkeypatch.setattr(services, "probe_service", lambda *args, **kwargs: {"version": "0.20.0"})
    found = services.discover_services(proc_root=tmp_path, current_pid=os.getpid())
    assert len(found) == 1
    assert found[0].pid == 123
    assert found[0].port == 8765
    assert found[0].version == "0.20.0"
    assert found[0].current is False


def test_non_videoflow_process_is_ignored(tmp_path: Path) -> None:
    make_proc(tmp_path, 124, 8766, b"/usr/bin/python\0script.py\0serve\0")
    assert services.discover_services(proc_root=tmp_path) == []


def test_stop_refuses_current_process(monkeypatch) -> None:
    monkeypatch.setattr(services, "process_alive", lambda _pid: True)
    assert services.stop_service_pid(os.getpid()) is False


def test_current_appimage_launcher_is_protected(monkeypatch, tmp_path: Path) -> None:
    make_proc(
        tmp_path,
        125,
        8767,
        b"/home/user/VideoFlow-0.22.2-x86_64.AppImage\0serve\0--open\0",
    )
    monkeypatch.setenv("APPIMAGE", "/home/user/VideoFlow-0.22.2-x86_64.AppImage")
    found = services.discover_services(proc_root=tmp_path, current_pid=os.getpid())
    assert len(found) == 1
    assert found[0].kind == "launcher"
    assert found[0].protected is True
