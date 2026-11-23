import json

from videoflow import __version__, cli


class FakeRun:
    def to_dict(self) -> dict[str, object]:
        return {"ok": True, "video_segment_count": 2, "artifacts": {}}


def test_version(capsys) -> None:
    assert cli.main(["version"]) == 0
    output = capsys.readouterr().out
    assert __version__ in output
    assert "videoflow" in output


def test_doctor_reports_missing_ffmpeg(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "find_binary", lambda _name: None)
    monkeypatch.setattr(cli, "find_silero_model", lambda: None)
    assert cli.main(["doctor"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["ffmpeg"]["found"] is False


def test_doctor_passes_when_tools_are_present(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))

    class Completed:
        returncode = 0
        stdout = "ffmpeg version test\n"
        stderr = ""

    monkeypatch.setattr(cli, "find_binary", lambda _name: "/usr/bin/tool")
    monkeypatch.setattr(cli.subprocess, "run", lambda *args, **kwargs: Completed())
    assert cli.main(["doctor"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True


def test_serve_ui_url_handles_wildcard_bind() -> None:
    assert cli._ui_url("127.0.0.1", 8765) == "http://127.0.0.1:8765/"
    assert cli._ui_url("0.0.0.0", 9000) == "http://127.0.0.1:9000/"
    assert cli._ui_url("::", 9001) == "http://127.0.0.1:9001/"


def test_unknown_command_returns_usage(capsys) -> None:
    assert cli.main([]) == 2
    assert "usage" in capsys.readouterr().out.lower()


def test_doctor_reports_faster_whisper(monkeypatch, tmp_path, capsys) -> None:
    class Completed:
        returncode = 0
        stdout = "ffmpeg version test\n"
        stderr = ""

    import sys
    from types import ModuleType

    model = tmp_path / "faster-whisper" / "small"
    model.mkdir(parents=True)
    package = ModuleType("faster_whisper")
    package.__version__ = "1.2.1"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", package)
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "find_binary", lambda _name: "/usr/bin/tool")
    monkeypatch.setattr(cli.subprocess, "run", lambda *args, **kwargs: Completed())
    monkeypatch.setattr(cli, "find_faster_whisper_model", lambda size="small": model)
    assert cli.main(["doctor"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["faster_whisper"]["model"] == str(model)
    assert payload["faster_whisper"]["found"] is True


def test_status_without_a_pid_file(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "discover_services", lambda: [])
    assert cli.main(["status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["running"] is False
    assert payload["pid"] is None


def test_stop_without_a_pid_file(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    assert cli.main(["stop"]) == 0
    assert "not running" in capsys.readouterr().out
