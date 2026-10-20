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


def test_run_prints_the_report(monkeypatch, tmp_path, capsys) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    monkeypatch.setattr(cli, "run_portable", lambda *args, **kwargs: FakeRun())
    assert cli.main(["run", str(source), "--out", str(tmp_path / "out")]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["video_segment_count"] == 2


def test_cull_retakes_requires_a_transcript(tmp_path, capsys) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    assert cli.main(["run", str(source), "--cull-retakes"]) == 2
    assert "--transcript" in capsys.readouterr().err


def test_serve_ui_url_handles_wildcard_bind() -> None:
    assert cli._ui_url("127.0.0.1", 8765) == "http://127.0.0.1:8765/"
    assert cli._ui_url("0.0.0.0", 9000) == "http://127.0.0.1:9000/"
    assert cli._ui_url("::", 9001) == "http://127.0.0.1:9001/"


def test_unknown_command_returns_usage(capsys) -> None:
    assert cli.main([]) == 2
    assert "usage" in capsys.readouterr().out.lower()


def test_run_passes_vad_options(monkeypatch, tmp_path, capsys) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    seen: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> FakeRun:
        seen.update(kwargs)
        return FakeRun()

    monkeypatch.setattr(cli, "run_portable", fake_run)
    assert (
        cli.main(
            [
                "run",
                str(source),
                "--out",
                str(tmp_path / "out"),
                "--vad-engine",
                "silero",
                "--speech-threshold",
                "0.6",
                "--speech-pad-before-ms",
                "10",
                "--speech-pad-after-ms",
                "20",
            ]
        )
        == 0
    )
    assert seen["vad_engine"] == "silero"
    assert seen["speech_threshold"] == 0.6
    assert seen["speech_pad_before_ms"] == 10
    assert seen["speech_pad_after_ms"] == 20
