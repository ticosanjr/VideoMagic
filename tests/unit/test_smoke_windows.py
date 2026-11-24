from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts import smoke_windows


def test_help_exits_without_side_effects(capsys) -> None:
    with pytest.raises(SystemExit) as captured:
        smoke_windows.main(["--help"])
    assert captured.value.code == 0
    assert "--exe" in capsys.readouterr().out


def test_clean_env_removes_build_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PYTHONPATH", "/tmp/site-packages")
    monkeypatch.setenv("VIRTUAL_ENV", "/tmp/venv")
    monkeypatch.setenv("VF_GPU_WORKER_URL", "http://worker:8080")
    env = smoke_windows.clean_env(tmp_path)
    assert "PYTHONPATH" not in env
    assert "VIRTUAL_ENV" not in env
    assert "VF_GPU_WORKER_URL" not in env
    assert env["VIDEOWFLOW_HOME"] == str(tmp_path)
    assert env["VIDEOWFLOW_ALLOWED_ROOTS"] == str(tmp_path)
    assert env["PATH"]


def test_clean_env_can_keep_the_current_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", "/custom/bin")
    env = smoke_windows.clean_env(tmp_path, keep_path=True)
    assert env["PATH"] == "/custom/bin"


def test_json_output_skips_leading_noise() -> None:
    payload = smoke_windows._json_output('warning: hi\n{"ok": true, "value": 2}\n')
    assert payload == {"ok": True, "value": 2}


def test_json_output_rejects_non_json() -> None:
    with pytest.raises(smoke_windows.SmokeError):
        smoke_windows._json_output("not json")


def test_mcp_tool_check_reports_a_complete_core_profile(monkeypatch, tmp_path: Path) -> None:
    class Completed:
        returncode = 0
        stderr = ""
        stdout = "\n".join(
            (*smoke_windows.CORE_TOOLS, "vf_project", "vf_jobs")
        )

    monkeypatch.setattr(smoke_windows, "run", lambda *args, **kwargs: Completed())
    tools = smoke_windows.check_mcp_tools(
        tmp_path / "videoflow", {"PATH": "/bin"}, timeout=1
    )
    assert set(smoke_windows.CORE_TOOLS) <= set(tools)


def test_mcp_tool_check_fails_on_missing_tools(monkeypatch, tmp_path: Path) -> None:
    class Completed:
        returncode = 0
        stderr = ""
        stdout = "vf_project\n"

    monkeypatch.setattr(smoke_windows, "run", lambda *args, **kwargs: Completed())
    with pytest.raises(smoke_windows.SmokeError):
        smoke_windows.check_mcp_tools(
            tmp_path / "videoflow", {"PATH": "/bin"}, timeout=1
        )


def test_default_exe_prefers_the_onedir_bundle(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    suffix = ".exe" if smoke_windows.os.name == "nt" else ""
    onedir = tmp_path / "dist" / "videoflow" / f"videoflow{suffix}"
    onedir.parent.mkdir(parents=True)
    onedir.write_text("", encoding="utf-8")
    assert smoke_windows.default_exe() == Path("dist") / "videoflow" / onedir.name


def test_zip_directory_is_stored_and_flat(tmp_path: Path) -> None:
    import zipfile

    from scripts.build_portable import zip_directory

    source = tmp_path / "bundle"
    (source / "ui").mkdir(parents=True)
    (source / "videoflow.exe").write_bytes(b"exe")
    (source / "ui" / "index.html").write_text("<html></html>", encoding="utf-8")
    archive = tmp_path / "bundle.zip"
    zip_directory(source, archive)
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        assert names == {"videoflow.exe", "ui/index.html"}
        assert all(item.compress_type == zipfile.ZIP_STORED for item in bundle.infolist())


def test_doctor_payload_contains_local_gpu_and_nvenc(monkeypatch, tmp_path: Path, capsys) -> None:
    from videoflow import cli

    class Completed:
        returncode = 0
        stdout = "ffmpeg version test\n"
        stderr = ""

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "find_binary", lambda _name: "/usr/bin/tool")
    monkeypatch.setattr(cli.subprocess, "run", lambda *args, **kwargs: Completed())
    assert cli.main(["doctor"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["local_gpu"] == {"available": False}
    assert isinstance(payload["nvenc"]["available"], bool)
    assert isinstance(payload["fonts"]["dirs"], list)


def test_mcp_list_tools_prints_the_core_profile(capsys) -> None:
    from videoflow import cli

    assert cli.main(["mcp", "--profile", "core", "--list-tools"]) == 0
    names = capsys.readouterr().out.split()
    assert "vf_style" in names
    assert len(names) == 18


def test_zip_directory_can_deflate_for_release(tmp_path: Path) -> None:
    import zipfile

    from scripts.build_portable import zip_directory

    source = tmp_path / "bundle"
    source.mkdir()
    (source / "payload.bin").write_bytes(b"a" * 200_000)
    archive = tmp_path / "bundle.zip"
    zip_directory(
        source,
        archive,
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=1,
    )
    with zipfile.ZipFile(archive) as bundle:
        assert all(
            item.compress_type == zipfile.ZIP_DEFLATED
            for item in bundle.infolist()
        )
    assert archive.stat().st_size < 100_000


def test_certify_windows_nvidia_help_exits_zero() -> None:
    from scripts import certify_windows_nvidia

    with pytest.raises(SystemExit) as error:
        certify_windows_nvidia.main(["--help"])
    assert error.value.code == 0
