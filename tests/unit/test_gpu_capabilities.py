from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

PACKAGE_SRC = Path(__file__).resolve().parents[2] / "packages" / "gpu-worker" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from gpu_worker import handlers_gpu  # noqa: E402
from gpu_worker.capabilities import VRAM_COST_MB  # noqa: E402
from gpu_worker.handlers import build_default_registry  # noqa: E402
from gpu_worker.models import ModelRegistry  # noqa: E402
from gpu_worker.settings import Settings  # noqa: E402
from vf_shared.compute.capabilities import VRAM_COST_MB as ROUTER_COSTS  # noqa: E402


def test_router_and_worker_vram_tables_match() -> None:
    assert VRAM_COST_MB == ROUTER_COSTS
    assert {
        "asr",
        "render_nvenc",
        "segment_matte",
        "face_track",
        "scene_analyze",
        "short_render",
    } <= set(VRAM_COST_MB)


def test_builtin_handlers_are_opt_in_and_report_missing_backends(
    tmp_path: Path,
) -> None:
    plain = build_default_registry(Settings(work_dir=tmp_path / "plain"))
    assert plain.is_available("asr") is False
    assert "VF_GPU_ASR_CMD" in plain.reason("asr")

    enabled = build_default_registry(
        Settings(
            work_dir=tmp_path / "enabled",
            builtin_handlers=True,
            ffmpeg_cmd="/bin/false",
        )
    )
    assert enabled.is_available("asr") is True
    assert enabled.is_available("face_track") is True
    assert enabled.is_available("scene_analyze") is True
    assert enabled.is_available("short_render") is True
    assert enabled.is_available("render_nvenc") is False
    assert "h264_nvenc" in enabled.reason("render_nvenc")
    assert "rembg" in enabled.reason("segment_matte")


def test_selftest_handler_is_always_available(tmp_path: Path) -> None:
    registry = build_default_registry(Settings(work_dir=tmp_path / "plain"))
    assert registry.is_available("selftest") is True


def test_matte_session_registers_in_model_registry(tmp_path: Path, monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    from gpu_worker.gpu_handlers import matte

    created: list[str] = []

    def new_session(name: str):
        created.append(name)
        return object()

    monkeypatch.setitem(sys.modules, "rembg", SimpleNamespace(new_session=new_session))
    models = ModelRegistry(ttl_seconds=60)
    first = matte._matte_session("u2net", models)
    second = matte._matte_session("u2net", models)
    assert first is second
    assert created == ["u2net"]
    assert "rembg:u2net" in {item["name"] for item in models.snapshot()}


def test_worker_version_is_not_hardcoded() -> None:
    from gpu_worker import __version__

    assert __version__ != "2.90.0"
    assert __version__


def test_asr_handler_writes_word_aligned_json(tmp_path: Path, monkeypatch) -> None:
    class Words:
        def __init__(self) -> None:
            self.word = " olá"
            self.start = 0.0
            self.end = 0.4
            self.probability = 0.9

    class Segment:
        start = 0.0
        end = 0.4
        text = " olá"
        words = [Words()]

    class Model:
        def transcribe(self, path, **kwargs):
            assert kwargs["language"] == "pt"
            return [Segment()], SimpleNamespace(language="pt", language_probability=0.98)

    key = ("large-v3-turbo", "cpu", "int8")
    monkeypatch.setitem(handlers_gpu._ASR_MODELS, key, Model())
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"wav")
    handler = handlers_gpu.make_asr_handler(
        Settings(
            work_dir=tmp_path / "worker",
            asr_model="large-v3-turbo",
            asr_device="cpu",
            asr_compute_type="int8",
        )
    )
    outputs = handler({}, [audio], tmp_path / "work")
    assert outputs and outputs[0].is_file()
    import json

    payload = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert payload["segments"][0]["text"] == "olá"
    assert payload["segments"][0]["words"][0]["word"] == " olá"


def test_forced_align_handler_writes_alignment_json(tmp_path: Path, monkeypatch) -> None:
    class Words:
        word = " olá"
        start = 0.0
        end = 0.4
        probability = 0.9

    class Segment:
        start = 0.0
        end = 0.4
        text = " olá"
        words = [Words()]

    class Model:
        def transcribe(self, path, **kwargs):
            return [Segment()], SimpleNamespace(language="pt", language_probability=0.98)

    key = ("large-v3-turbo", "cpu", "int8")
    monkeypatch.setitem(handlers_gpu._ASR_MODELS, key, Model())
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"wav")
    handler = handlers_gpu.make_forced_align_handler(
        Settings(
            work_dir=tmp_path / "worker",
            asr_model="large-v3-turbo",
            asr_device="cpu",
            asr_compute_type="int8",
        )
    )
    outputs = handler({"language": "pt"}, [audio], tmp_path / "work")
    assert outputs and outputs[0].name == "alignment.json"
    payload = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert payload["segments"][0]["words"][0]["word"] == " olá"


def test_render_nvenc_handler_builds_nvenc_command(tmp_path: Path, monkeypatch) -> None:
    commands: list[list[str]] = []

    def fake_run(tokens: list[str], *, timeout: float = 3600.0) -> None:
        commands.append(tokens)
        Path(tokens[-1]).write_bytes(b"mp4")

    from gpu_worker.gpu_handlers import render as render_handlers

    monkeypatch.setattr(render_handlers, "_run", fake_run)
    monkeypatch.setattr(
        render_handlers, "nvenc_available", lambda ffmpeg="ffmpeg": True
    )
    monkeypatch.setattr(
        render_handlers,
        "nvenc_args",
        lambda ffmpeg="ffmpeg": ["-preset", "p4", "-rc", "vbr", "-cq", "20", "-b:v", "0"],
    )
    base = tmp_path / "base.mp4"
    base.write_bytes(b"base")
    ass = tmp_path / "captions.ass"
    ass.write_text("Style: Default", encoding="utf-8")
    handler = handlers_gpu.make_render_nvenc_handler(
        Settings(work_dir=tmp_path / "worker", builtin_handlers=True)
    )
    outputs = handler(
        {"ass_path": str(ass), "width": 1080, "height": 1920, "fps": 30},
        [base],
        tmp_path / "work",
    )
    assert outputs and outputs[0].is_file()
    command = commands[0]
    assert "h264_nvenc" in command
    assert any("ass=" in token for token in command)
    assert "scale=1080:1920" in " ".join(command)


def test_nvenc_probe_is_cached(monkeypatch) -> None:
    calls: list[list[str]] = []

    class Completed:
        returncode = 0
        stdout = " V....D h264_nvenc"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[-1].endswith(".mp4"):
            Path(command[-1]).write_bytes(b"x" * 2048)
            return Completed()
        return Completed()

    from gpu_worker.gpu_handlers import common as handler_common

    monkeypatch.setattr(handler_common.subprocess, "run", fake_run)
    handlers_gpu._NVENC_CACHE.clear()
    handlers_gpu._NVENC_PROBES.clear()
    assert handlers_gpu.nvenc_available("/fake/ffmpeg") is True
    assert handlers_gpu.nvenc_available("/fake/ffmpeg") is True
    assert len(calls) == 2
    assert "h264_nvenc" in calls[1]
    assert "-pix_fmt" in calls[1]


def test_nvenc_probe_falls_back_from_invalid_options(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[-1] == "-encoders" or "-encoders" in command:
            return SimpleNamespace(returncode=0, stdout=" V....D h264_nvenc", stderr="")
        if len(calls) == 2:
            return SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="[h264_nvenc] Invalid argument",
            )
        Path(command[-1]).write_bytes(b"x" * 2048)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    from gpu_worker.gpu_handlers import common as handler_common

    monkeypatch.setattr(handler_common.subprocess, "run", fake_run)
    handlers_gpu._NVENC_PROBES.clear()
    probe = handlers_gpu.probe_nvenc("/fake/ffmpeg")
    assert probe.available is True
    assert probe.args == ("-preset", "p4", "-tune", "hq", "-rc", "constqp", "-qp", "23")
    assert len(calls) == 3


def test_nvenc_probe_reports_actionable_advice(monkeypatch) -> None:
    def fake_run(command, **kwargs):
        if "-encoders" in command:
            return SimpleNamespace(returncode=0, stdout=" h264_nvenc", stderr="")
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="[h264_nvenc] Cannot load libnvidia-encode.so.1",
        )

    from gpu_worker.gpu_handlers import common as handler_common

    monkeypatch.setattr(handler_common.subprocess, "run", fake_run)
    handlers_gpu._NVENC_PROBES.clear()
    probe = handlers_gpu.probe_nvenc("/fake/ffmpeg")
    assert probe.available is False
    assert "driver" in probe.advice.casefold()


def test_asr_retries_without_vad_when_onnx_is_broken(tmp_path: Path) -> None:
    class Words:
        word = " ola"
        start = 0.0
        end = 0.4
        probability = 0.9

    class Segment:
        start = 0.0
        end = 0.4
        text = " ola"
        words = [Words()]

    class Model:
        def __init__(self) -> None:
            self.calls: list[bool] = []

        def transcribe(self, path, **kwargs):
            self.calls.append(bool(kwargs["vad_filter"]))
            if kwargs["vad_filter"]:
                raise AttributeError(
                    "module 'onnxruntime' has no attribute 'SessionOptions'"
                )
            return [Segment()], SimpleNamespace(language="pt", language_probability=0.9)

    model = Model()
    key = ("large-v3-turbo", "cpu", "int8")
    handlers_gpu._ASR_MODELS[key] = model
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"wav")
    handler = handlers_gpu.make_asr_handler(
        Settings(
            work_dir=tmp_path / "worker",
            asr_model="large-v3-turbo",
            asr_device="cpu",
            asr_compute_type="int8",
        )
    )
    outputs = handler({"vad_filter": True}, [audio], tmp_path / "work")
    payload = json.loads(Path(outputs[0]).read_text(encoding="utf-8"))
    assert model.calls == [True, False]
    assert payload["vad_fallback"] is True
    assert "SessionOptions" in payload["vad_error"]
    assert payload["segments"][0]["text"] == "ola"
