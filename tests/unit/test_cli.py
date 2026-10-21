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


def test_run_passes_faster_whisper_options(monkeypatch, tmp_path, capsys) -> None:
    from videoflow.domain.config import TranscribeConfig

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    model = tmp_path / "faster-whisper-medium"
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
                "--transcribe",
                "--whisper-engine",
                "faster-whisper",
                "--model-size",
                "medium",
                "--device",
                "cuda",
                "--compute-type",
                "float16",
                "--whisper-vad",
                "--asr-language",
                "en",
                "--faster-whisper-model",
                str(model),
            ]
        )
        == 0
    )
    config = seen["transcribe_config"]
    assert isinstance(config, TranscribeConfig)
    assert config.engine == "faster-whisper"
    assert config.model_size == "medium"
    assert config.language == "en"
    assert config.device == "cuda"
    assert config.compute_type == "float16"
    assert config.vad_filter is True
    assert seen["faster_whisper_model"] == model
    assert seen["asr_language"] == "en"


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


def test_run_passes_short_and_detailed_config_options(monkeypatch, tmp_path, capsys) -> None:
    from videoflow.domain.config import JlCutsConfig, ShortsConfig, ZoomsConfig

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
                "--transcribe",
                "--shorts",
                "--shorts-count",
                "3",
                "--shorts-min-count",
                "3",
                "--shorts-min-sec",
                "10",
                "--shorts-max-sec",
                "20",
                "--shorts-selection-mode",
                "heuristic",
                "--shorts-aspect",
                "16:9",
                "--shorts-prompt",
                "pricing",
                "--shorts-reprompt",
                "more energy",
                "--shorts-prompt-mode",
                "refine",
                "--shorts-hook-mode",
                "repeat",
                "--shorts-remove-fillers",
                "--shorts-filler-word",
                "um",
                "--caption-censor",
                "--caption-censor-word",
                "merda",
                "--audio-enhance",
                "--shorts-start-sec",
                "5",
                "--shorts-end-sec",
                "50",
                "--zoom-min-scale",
                "1.1",
                "--zoom-max-scale",
                "1.9",
                "--fade-in-ms",
                "30",
                "--fade-out-ms",
                "40",
                "--fade-curve",
                "linear",
            ]
        )
        == 0
    )
    assert seen["shorts"] is True
    assert seen["shorts_count"] == 3
    assert isinstance(seen["shorts_config"], ShortsConfig)
    assert seen["shorts_config"].min_clips == 3
    assert seen["shorts_config"].selection_mode == "heuristic"
    assert seen["shorts_config"].aspect_ratio == "16:9"
    assert seen["shorts_config"].prompt == "pricing"
    assert seen["shorts_config"].reprompt == "more energy"
    assert seen["shorts_config"].prompt_mode == "refine"
    assert seen["shorts_config"].hook_mode == "repeat"
    assert seen["shorts_config"].remove_fillers is True
    assert seen["shorts_config"].filler_words == ["um"]
    assert seen["shorts_config"].caption_style.censor_enabled is True
    assert seen["shorts_config"].caption_style.censor_words == ["merda"]
    assert seen["audio_filters"] == (
        "highpass=f=80",
        "afftdn=nr=12:nf=-30",
        "loudnorm=I=-16.0:TP=-1.5:LRA=11",
    )
    assert seen["shorts_config"].source_start_sec == 5
    assert seen["shorts_config"].source_end_sec == 50
    assert isinstance(seen["jl"], JlCutsConfig)
    assert seen["jl"].fade_in_ms == 30
    assert seen["jl"].fade_out_ms == 40
    assert seen["jl"].fade_curve == "linear"
    assert isinstance(seen["zooms"], ZoomsConfig)
    assert seen["zooms"].min_scale == 1.1
    assert seen["zooms"].max_scale == 1.9


def test_status_without_a_pid_file(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    assert cli.main(["status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["running"] is False
    assert payload["pid"] is None


def test_stop_without_a_pid_file(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    assert cli.main(["stop"]) == 0
    assert "not running" in capsys.readouterr().out
