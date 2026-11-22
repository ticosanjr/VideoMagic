"""Unit tests for the isolated VideoFlow 2.90 audio and vision MCP packages."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _package in ("mcp-audio", "mcp-vision"):
    _src = ROOT / "packages" / _package / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

from videoflow.domains.audio import studio as audio_tools  # noqa: E402
from videoflow.domains.audio import studio_common as audio_common  # noqa: E402
from videoflow.domains.toolkit import commands as audio_commands  # noqa: E402
from videoflow.domains.toolkit import commands as vision_commands  # noqa: E402
from videoflow.domains.toolkit import storage as audio_storage  # noqa: E402
from videoflow.domains.toolkit import storage as vision_storage  # noqa: E402
from videoflow.domains.toolkit.errors import (  # noqa: E402
    InvalidArgumentError,
    MissingCommandError,
)
from videoflow.domains.toolkit.errors import (  # noqa: E402
    InvalidArgumentError as VisionInvalidArgumentError,
)
from videoflow.domains.toolkit.errors import (  # noqa: E402
    MissingCommandError as VisionMissingCommandError,
)
from videoflow.domains.toolkit.router import RouterBridge as AudioRouterBridge  # noqa: E402
from videoflow.domains.toolkit.router import RouterBridge as VisionRouterBridge  # noqa: E402
from videoflow.domains.vision import captions as vision_captions  # noqa: E402
from videoflow.domains.vision import capture as vision_capture  # noqa: E402
from videoflow.domains.vision import common as vision_common  # noqa: E402
from videoflow.domains.vision import graphics_web as vision_graphics  # noqa: E402
from videoflow.domains.vision import tools as vision_tools  # noqa: E402

_ENV_KEYS = (
    "VF_PROJECT_OUTPUT",
    "VF_PROJECTS_ROOT",
    "VF_WORKSPACE_ROOT",
    "VF_POCKET_TTS_CMD",
    "VF_PIPER_CMD",
    "VF_DEEPFILTER_CMD",
    "VF_AUDIO_SEPARATOR_CMD",
    "VF_REALESRGAN_CMD",
    "VF_REMOTION_CMD",
    "VF_MANIM_CMD",
    "VF_WHISPER_BIN",
    "VF_WHISPER_MODEL",
    "VF_REMBG_CMD",
    "VF_BROLL_SIZE",
)


class FakeRouter:
    """Minimal stand-in for `vf_shared.compute.ComputeRouter`."""

    def __init__(self, healthy: set[str] | None = None, remote_file: Path | None = None) -> None:
        self.healthy = set(healthy or set())
        self.remote_file = remote_file
        self.health_calls: list[str] = []
        self.calls: list[tuple[str, dict[str, object]]] = []

    def health(self, capability: str) -> bool:
        self.health_calls.append(capability)
        return capability in self.healthy

    def submit(self, capability: str, payload: dict[str, object]) -> dict[str, str]:
        self.calls.append((capability, payload))
        if self.remote_file is None:
            return {}
        return {"path": str(self.remote_file)}


@pytest.fixture()
def project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    workspace = tmp_path / "workspace"
    root = workspace / "projects"
    root.mkdir(parents=True)
    monkeypatch.setenv("VF_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("VF_PROJECTS_ROOT", str(root))
    return root


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(audio_common, "ROUTER", AudioRouterBridge(FakeRouter()))
    monkeypatch.setattr(vision_common, "ROUTER", VisionRouterBridge(FakeRouter()))


@pytest.fixture()
def fake_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "ffmpeg"
    script.write_text('#!/bin/sh\nfor last; do :; done\nprintf "MEDIA" > "$last"\n')
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    return script


def _write_tts_helper(tmp_path: Path) -> Path:
    script = tmp_path / "fake_tts.py"
    script.write_text(
        "import pathlib, sys\n"
        "out = pathlib.Path(sys.argv[1])\n"
        "text = sys.argv[2]\n"
        "out.parent.mkdir(parents=True, exist_ok=True)\n"
        "out.write_bytes(b'RIFF')\n"
        "(out.parent / 'text.txt').write_text(text)\n"
        "log = out.parent / 'runs.txt'\n"
        "log.write_text((log.read_text() if log.exists() else '') + 'x')\n",
        encoding="utf-8",
    )
    return script


def test_expand_template_keeps_spaces_and_metacharacters_as_one_argument() -> None:
    argv = audio_commands.expand_template(
        "/opt/tool --text {text} --out {output}",
        {"text": "olá mundo & mais", "output": "/tmp/a.wav"},
    )
    assert argv == ["/opt/tool", "--text", "olá mundo & mais", "--out", "/tmp/a.wav"]


def test_expand_template_rejects_unknown_placeholder() -> None:
    with pytest.raises(InvalidArgumentError):
        audio_commands.expand_template("tool {missing}", {})


def test_run_uses_argv_without_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(audio_commands.subprocess, "run", fake_run)
    result = audio_commands.run(["echo", "hi"])

    assert captured["argv"] == ["echo", "hi"]
    assert "shell" not in captured["kwargs"]
    assert result.returncode == 0


def test_run_missing_executable_is_typed(tmp_path: Path) -> None:
    with pytest.raises(MissingCommandError) as info:
        audio_commands.run([str(tmp_path / "does-not-exist")])
    assert info.value.code == "missing_command"


def test_tts_writes_sidecar_and_reuses_cache(
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = _write_tts_helper(tmp_path)
    monkeypatch.setenv(
        "VF_POCKET_TTS_CMD",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(helper))} {{output}} {{text}}",
    )

    first = audio_tools.tts_generate("proj-tts", "olá mundo & mais")
    output = Path(first["output"])
    assert output.is_file()
    assert first["cached"] is False
    assert output.relative_to(project_root / "proj-tts") == Path(first["relative_path"])
    assert (output.parent / "text.txt").read_text(encoding="utf-8") == "olá mundo & mais"

    sidecar = Path(first["sidecar"])
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["license"] == "ai_generated"
    assert payload["source"] == "local:pocket-tts"
    assert payload["ai_generated"] is True
    assert payload["cache_key"] == first["cache_key"]
    assert payload["sha256"] == first["sha256"]

    second = audio_tools.tts_generate("proj-tts", "olá mundo & mais")
    assert second["cached"] is True
    assert (output.parent / "runs.txt").read_text(encoding="utf-8") == "x"


def test_mix_graph_contains_sidechain_and_loudnorm() -> None:
    graph = audio_tools.build_mix_graph(
        has_music=True,
        sfx_count=1,
        target_lufs=-14.0,
        sfx_starts=[1.5],
        sfx_gains=[-6.0],
    )
    assert "sidechaincompress" in graph
    assert "loudnorm=I=-14.0" in graph
    assert "adelay=1500|1500" in graph
    assert "amix=inputs=3" in graph


def test_mix_and_master_writes_assets(
    project_root: Path,
    fake_ffmpeg: Path,
    tmp_path: Path,
) -> None:
    voice = tmp_path / "voice.wav"
    voice.write_bytes(b"VOICE")
    music = tmp_path / "music.wav"
    music.write_bytes(b"MUSIC")
    sfx = tmp_path / "whoosh.wav"
    sfx.write_bytes(b"SFX")

    result = audio_tools.mix_and_master_track(
        "proj-mix",
        str(voice),
        music_path=str(music),
        sfx_events=[{"path": str(sfx), "start": 0.5, "gain_db": -4.0}],
        target_lufs=-14.0,
    )
    output = Path(result["output"])
    assert output.is_file()
    assert output.name == "master.wav"
    assert output == project_root / "proj-mix" / "assets" / "audio" / "master.wav"
    assert result["ducking"] is True
    assert result["sfx_count"] == 1
    payload = json.loads(Path(result["sidecar"]).read_text(encoding="utf-8"))
    assert payload["source"] == "ffmpeg:mix"
    assert payload["license"] == "ai_generated"
    assert payload["metadata"]["ducking"] is True


def test_router_remote_tts_when_health_is_true(
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = tmp_path / "remote.wav"
    remote.write_bytes(b"REMOTE")
    fake = FakeRouter({"tts"}, remote)
    monkeypatch.setattr(audio_common, "ROUTER", AudioRouterBridge(fake))

    result = audio_tools.tts_generate("proj-remote", "fala", quality="final")

    assert result["mode"] == "remote"
    assert fake.calls and fake.calls[0][0] == "tts"
    assert Path(result["output"]).is_file()
    payload = json.loads(Path(result["sidecar"]).read_text(encoding="utf-8"))
    assert payload["source"] == "remote:tts"


def test_router_unhealthy_tts_falls_back_to_local(
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = _write_tts_helper(tmp_path)
    monkeypatch.setenv(
        "VF_PIPER_CMD",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(helper))} {{output}} {{text}}",
    )
    fake = FakeRouter(set())
    monkeypatch.setattr(audio_common, "ROUTER", AudioRouterBridge(fake))

    result = audio_tools.tts_generate("proj-fallback", "fala", quality="final")

    assert result["mode"] == "local"
    assert fake.calls == []
    assert fake.health_calls == ["tts"]
    payload = json.loads(Path(result["sidecar"]).read_text(encoding="utf-8"))
    assert payload["source"] == "local:piper"


def test_tts_without_command_is_typed(project_root: Path) -> None:
    with pytest.raises(MissingCommandError) as info:
        audio_tools.tts_generate("proj-missing", "fala", quality="draft")
    assert info.value.code == "missing_command"
    assert "VF_POCKET_TTS_CMD" in str(info.value)


def test_assets_go_through_vf_contracts_writer(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    module = types.ModuleType("vf_shared.contracts")
    assets = types.ModuleType("vf_shared.contracts.assets")

    def write_asset(
        project_id: str,
        kind: str,
        source_path_or_bytes: str | Path | bytes,
        record_fields: dict[str, object] | None = None,
    ) -> dict[str, str]:
        fields = dict(record_fields or {})
        if isinstance(source_path_or_bytes, (bytes, bytearray)):
            content = bytes(source_path_or_bytes)
        else:
            content = Path(source_path_or_bytes).read_bytes()
        target = project_root / project_id / "assets" / kind / "stored.wav"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.with_name(target.name + ".meta.json").write_text(
            json.dumps({"params_hash": fields.get("params_hash", ""), **fields}),
            encoding="utf-8",
        )
        calls.append(
            {
                "project_id": project_id,
                "kind": kind,
                "content": content,
                "fields": fields,
            }
        )
        return {"path": f"assets/{kind}/stored.wav"}

    assets.write_asset = write_asset  # type: ignore[attr-defined]
    module.assets = assets  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "vf_shared.contracts", module)
    monkeypatch.setitem(sys.modules, "vf_shared.contracts.assets", assets)

    record = audio_storage.write_output(
        "proj-writer",
        "assets/audio/x.wav",
        data=b"RIFF",
        kind="audio",
        source="test",
        license="generated",
        cache_key="abc123",
        ai_generated=True,
    )

    assert record.path.is_file()
    assert record.path.read_bytes() == b"RIFF"
    assert calls == [
        {
            "project_id": "proj-writer",
            "kind": "voice",
            "content": b"RIFF",
            "fields": {
                "license": "ai_generated",
                "source": "test",
                "params_hash": "abc123",
                "ext": ".wav",
                "provider": "local",
            },
        }
    ]


def test_image_to_broll_writes_assets_with_fake_ffmpeg(
    project_root: Path,
    fake_ffmpeg: Path,
    tmp_path: Path,
) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"PNG")

    result = vision_tools.image_to_broll_motion(
        "proj-broll",
        str(image),
        duration_sec=2.0,
        motion="zoom_in",
    )
    output = Path(result["output"])
    assert output.is_file()
    assert output.relative_to(project_root / "proj-broll") == Path("assets/broll/frame_zoom_in.mp4")
    payload = json.loads(Path(result["sidecar"]).read_text(encoding="utf-8"))
    assert payload["source"] == "ffmpeg:broll"
    assert payload["metadata"]["motion"] == "zoom_in"

    again = vision_tools.image_to_broll_motion(
        "proj-broll",
        str(image),
        duration_sec=2.0,
        motion="zoom_in",
    )
    assert again["cached"] is True


def test_image_to_broll_uses_aspect_and_project_canvas(
    project_root: Path,
    fake_ffmpeg: Path,
    tmp_path: Path,
) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"PNG")
    project = project_root / "proj-broll-aspect"
    project.mkdir(parents=True)
    (project / "project_state.json").write_text(
        json.dumps(
            {
                "media_info": {
                    "width": 1080,
                    "height": 1920,
                }
            }
        ),
        encoding="utf-8",
    )
    result = vision_tools.image_to_broll_motion(
        "proj-broll-aspect",
        str(image),
        duration_sec=1.0,
        motion="zoom_in",
        aspect_ratio="4:5",
    )
    payload = json.loads(Path(result["sidecar"]).read_text(encoding="utf-8"))
    assert (payload["metadata"]["width"], payload["metadata"]["height"]) == (1080, 1350)
    assert "1080x1350" in Path(result["output"]).name

    with pytest.raises(VisionInvalidArgumentError):
        vision_tools.image_to_broll_motion(
            "proj-broll-aspect",
            str(image),
            aspect_ratio="bad",
        )


def test_graphic_dimensions_follow_a_vertical_project(project_root: Path) -> None:
    project = project_root / "proj-vertical"
    project.mkdir(parents=True)
    (project / "project_state.json").write_text(
        json.dumps({"media_info": {"width": 1080, "height": 1920}}),
        encoding="utf-8",
    )
    assert vision_tools._graphic_dimensions("proj-vertical", 0, 0) == (1080, 1920)


def test_upscale_ffmpeg_fallback_is_marked(
    project_root: Path,
    fake_ffmpeg: Path,
    tmp_path: Path,
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"MP4")

    result = vision_tools.upscale_media("proj-up", str(source), scale=2)

    assert result["fallback"] is True
    assert Path(result["output"]).name == "clip_x2.mp4"
    payload = json.loads(Path(result["sidecar"]).read_text(encoding="utf-8"))
    assert payload["metadata"]["fallback"] is True


def test_render_motion_graphic_expands_template(
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = tmp_path / "fake_remotion.py"
    helper.write_text(
        "import json, pathlib, sys\n"
        "props = json.loads(pathlib.Path(sys.argv[2]).read_text())\n"
        "out = pathlib.Path(sys.argv[3])\n"
        "out.parent.mkdir(parents=True, exist_ok=True)\n"
        "out.write_bytes(json.dumps({'props': props, 'duration': sys.argv[4]}).encode())\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "VF_REMOTION_CMD",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(helper))} "
        "{entry} {props} {output} {duration}",
    )

    result = vision_tools.render_motion_graphic(
        "proj-gfx",
        engine="remotion",
        template_or_code="Intro.tsx",
        props_json='{"title": "Olá"}',
        duration_sec=3.5,
    )

    assert Path(result["output"]).is_file()
    assert result["source"] == "local:remotion"
    rendered = json.loads(Path(result["output"]).read_text(encoding="utf-8"))
    assert rendered == {"props": {"title": "Olá"}, "duration": "3.500"}


def test_render_motion_rejects_unknown_engine(project_root: Path) -> None:
    with pytest.raises(VisionInvalidArgumentError):
        vision_tools.render_motion_graphic("proj-gfx", "blender", "scene", "{}", 2.0)


def test_render_motion_without_command_is_typed(project_root: Path) -> None:
    with pytest.raises(VisionMissingCommandError) as info:
        vision_tools.render_motion_graphic("proj-gfx", "remotion", "Intro.tsx", "{}", 2.0)
    assert info.value.code == "missing_command"
    assert "VF_REMOTION_CMD" in str(info.value)


def test_transcribe_without_binary_is_typed(
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio = tmp_path / "speech.wav"
    audio.write_bytes(b"RIFF")
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.setattr(vision_captions, "_stable_whisper_available", lambda: False)

    with pytest.raises(VisionMissingCommandError) as info:
        vision_tools.transcribe_word_aligned("proj-asr", str(audio))

    assert info.value.code == "missing_command"
    assert "VF_WHISPER_BIN" in str(info.value)


def test_caption_formatting_helpers() -> None:
    segments = [
        {"start": 0.0, "end": 1.25, "text": "Olá"},
        {"start": 1.25, "end": 2.5, "text": "mundo"},
    ]
    srt = vision_tools.segments_to_srt(segments)
    assert "00:00:00,000 --> 00:00:01,250" in srt
    assert srt.startswith("1\n")

    ass = vision_tools.segments_to_ass(segments)
    assert "[Events]" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:01.25,Karaoke" in ass


def _fake_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    import contextlib as _contextlib

    @_contextlib.contextmanager
    def capture(*args: object, **kwargs: object):
        def grab(moment: float) -> bytes:
            return b"PNG"

        yield grab

    monkeypatch.setattr(vision_graphics, "_cdp_frame_capture", capture)
    monkeypatch.setattr(vision_capture, "_cdp_frame_capture", capture)


def _fake_chrome(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    script = tmp_path / "fake-chrome"
    script.write_text(
        f"#!{sys.executable}\n"
        "import pathlib, sys\n"
        "for arg in sys.argv:\n"
        "    if arg.startswith('--screenshot='):\n"
        "        target = pathlib.Path(arg.split('=', 1)[1])\n"
        "        target.parent.mkdir(parents=True, exist_ok=True)\n"
        "        target.write_bytes(b'PNG')\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("VF_CHROME_BIN", str(script))
    return script


def test_render_html_graphic_uses_sha256_cache(
    project_root: Path,
    tmp_path: Path,
    fake_ffmpeg: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_chrome(tmp_path, monkeypatch)
    _fake_capture(monkeypatch)
    source = tmp_path / "scene"
    source.mkdir()
    (source / "index.html").write_text("<html><body>Hello</body></html>", encoding="utf-8")

    result = vision_tools.render_motion_graphic(
        "proj-html",
        engine="hyperframes",
        template_or_code=str(source),
        duration_sec=0.1,
    )

    output = Path(result["output"])
    assert output.is_file()
    assert output.suffix == ".mp4"
    payload = json.loads(Path(result["sidecar"]).read_text(encoding="utf-8"))
    assert payload["metadata"]["engine"] == "hyperframes"
    assert len(payload["metadata"]["source_sha256"]) == 64

    again = vision_tools.render_motion_graphic(
        "proj-html",
        engine="hyperframes",
        template_or_code=str(source),
        duration_sec=0.1,
    )
    assert again["cached"] is True


def test_render_html_graphic_alpha_writes_webm(
    project_root: Path,
    tmp_path: Path,
    fake_ffmpeg: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_chrome(tmp_path, monkeypatch)
    _fake_capture(monkeypatch)
    source = tmp_path / "scene"
    source.mkdir()
    (source / "index.html").write_text("<html></html>", encoding="utf-8")

    result = vision_tools.render_motion_graphic(
        "proj-alpha",
        engine="html",
        template_or_code=str(source),
        duration_sec=0.1,
        alpha=True,
        draft_scale=0.5,
    )

    assert Path(result["output"]).suffix == ".webm"
    payload = json.loads(Path(result["sidecar"]).read_text(encoding="utf-8"))
    assert payload["metadata"]["alpha"] is True
    assert payload["metadata"]["draft_scale"] == 0.5


def test_capture_web_or_screen_screenshot_with_crop(
    project_root: Path,
    tmp_path: Path,
    fake_ffmpeg: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_chrome(tmp_path, monkeypatch)

    result = vision_tools.capture_web_or_screen(
        "proj-capture",
        "https://example.test/dashboard",
        mode="screenshot",
        crop_selector="10,20,300,200",
        output_name="dashboard",
    )

    assert Path(result["output"]).name == "dashboard.png"
    assert Path(result["output"]).is_file()
    payload = json.loads(Path(result["sidecar"]).read_text(encoding="utf-8"))
    assert payload["metadata"]["crop_filter"] == "crop=300:200:10:20"


def test_capture_web_or_screen_clip(
    project_root: Path,
    tmp_path: Path,
    fake_ffmpeg: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_chrome(tmp_path, monkeypatch)
    _fake_capture(monkeypatch)

    result = vision_tools.capture_web_or_screen(
        "proj-capture",
        "https://example.test",
        mode="clip",
        duration_sec=0.2,
        fps=5,
        output_name="scroll",
    )

    assert Path(result["output"]).name == "scroll.mp4"
    payload = json.loads(Path(result["sidecar"]).read_text(encoding="utf-8"))
    assert payload["metadata"]["mode"] == "clip"
    assert payload["metadata"]["fps"] == 5


def test_screen_target_detection() -> None:
    assert vision_tools._is_screen_target("screen") is True
    assert vision_tools._is_screen_target("SCREEN:0") is True
    assert vision_tools._is_screen_target("https://example.test") is False


def test_screen_capture_requires_display(project_root: Path, monkeypatch) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)
    with pytest.raises(VisionMissingCommandError) as info:
        vision_tools.capture_web_or_screen("proj-screen", "screen", mode="screenshot")
    assert info.value.code == "missing_command"


def test_screen_capture_screenshot_and_clip(
    project_root: Path,
    tmp_path: Path,
    fake_ffmpeg: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISPLAY", ":99")

    shot = vision_tools.capture_web_or_screen(
        "proj-screen",
        "screen",
        mode="screenshot",
        output_name="desktop",
    )
    assert Path(shot["output"]).name == "desktop.png"
    payload = json.loads(Path(shot["sidecar"]).read_text(encoding="utf-8"))
    assert payload["source"] == "screen::99"

    clip = vision_tools.capture_web_or_screen(
        "proj-screen",
        "screen",
        mode="clip",
        duration_sec=0.5,
        fps=5,
        output_name="scroll",
    )
    assert Path(clip["output"]).name == "scroll.mp4"


def test_upscale_remote_image_uses_the_source_extension(
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "still.png"
    source.write_bytes(b"PNG")
    remote = tmp_path / "remote.png"
    remote.write_bytes(b"UPSCALED")
    router = FakeRouter(healthy={"upscale"}, remote_file=remote)
    monkeypatch.setattr(vision_common, "ROUTER", VisionRouterBridge(router))

    result = vision_tools.upscale_media("proj-up", str(source), scale=2)

    assert result["mode"] == "remote"
    assert Path(result["output"]).name == "still_x2.png"
    assert router.calls[0][1]["output_name"] == "upscaled.png"
    assert router.calls[0][1]["is_video"] is False


def test_upscale_ffmpeg_video_preserves_audio_and_faststart(
    project_root: Path,
    tmp_path: Path,
    fake_ffmpeg: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"MP4")
    captured: list[list[str]] = []
    original = vision_commands.run

    def fake_run(argv, **kwargs):
        captured.append([str(item) for item in argv])
        return original(argv, **kwargs)

    monkeypatch.setattr(vision_commands, "run", fake_run)

    result = vision_tools.upscale_media("proj-up", str(source), scale=2, backend="ffmpeg")

    command = captured[-1]
    assert result["fallback"] is True
    assert "-map" in command and "0:a?" in command
    assert "+faststart" in command
    assert command[-1].endswith("clip_x2.mp4")


def test_realesrgan_video_pipeline_uses_frames_and_audio(
    tmp_path: Path,
    fake_ffmpeg: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"MP4")
    target = tmp_path / "out.mp4"
    captured: list[list[str]] = []

    def fake_run(argv, **kwargs):
        captured.append([str(item) for item in argv])
        return None

    monkeypatch.setattr(vision_commands, "run", fake_run)

    vision_tools._realesrgan_video(
        source, target, binary="/usr/bin/realesrgan-ncnn-vulkan", scale=2
    )

    assert len(captured) == 3
    assert "frame-%08d.png" in " ".join(captured[0])
    assert captured[1][-4:] == ["-o", str(captured[1][-3]), "-s", "2"] or "2" in captured[1]
    assert "1:a?" in captured[2]
    assert "+faststart" in captured[2]


def test_write_output_resolves_contracts_copy_when_project_output_differs(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VF_PROJECT_OUTPUT may differ from the shared workspace root."""

    override = tmp_path / "override"
    monkeypatch.setenv("VF_PROJECT_OUTPUT", str(override))

    record = audio_storage.write_output(
        "proj-override",
        "assets/voice/line.wav",
        data=b"RIFFdata",
        kind="audio",
        source="test",
        license="generated",
        cache_key="override-key",
    )

    assert record.path == override / "assets/voice/line.wav"
    assert record.path.read_bytes() == b"RIFFdata"
    assert record.sidecar.is_file()
    assert not (project_root / "proj-override/assets/voice/line.wav").exists()


def test_vision_write_output_resolves_contracts_copy_when_project_output_differs(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    override = tmp_path / "override"
    monkeypatch.setenv("VF_PROJECT_OUTPUT", str(override))

    record = vision_storage.write_output(
        "proj-override",
        "assets/images/still.png",
        data=b"PNGdata",
        kind="images",
        source="test",
        license="generated",
        cache_key="override-key",
    )

    assert record.path == override / "assets/images/still.png"
    assert record.path.read_bytes() == b"PNGdata"
    assert record.sidecar.is_file()


def test_generated_assets_use_the_ai_generated_contract_license() -> None:

    assert audio_storage.contract_license("generated") == "ai_generated"
    assert vision_storage.contract_license("generated") == "ai_generated"
    assert audio_storage.contract_license("source") == "unknown"
