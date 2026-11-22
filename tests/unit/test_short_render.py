from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application.short_composition.plan import resolve_draft
from videoflow.application.short_composition.planner import deterministic_draft
from videoflow.application.short_composition.render import (
    SegmentRender,
    SfxRenderCue,
    build_commands,
    build_segment_renders,
    execute_commands,
    nvenc_available,
    segment_filter,
)
from videoflow.domain.errors import IngestError
from videoflow.domain.scenes import SceneEntry, ScenesManifest
from videoflow.steps.base import StepIO


def _manifest(width: int = 1920, height: int = 1080, topology: str = "single_16x9"):
    def scene(scene_id: str, start: float, end: float, layout: str, hints: list[str]):
        return SceneEntry(
            scene_id=scene_id,
            start_sample=round(start * 48_000),
            end_sample=round(end * 48_000),
            start_sec=start,
            end_sec=end,
            layout_type=layout,  # type: ignore[arg-type]
            face_count=1,
            face_bbox_norm={"cx": 0.5, "cy": 0.4, "w": 0.2, "h": 0.3},
            face_area_ratio=0.06,
            edge_density=0.2 if layout.startswith("SCREEN") else 0.02,
            sharpness_laplacian=120.0,
            editing_hints=hints,
        )

    return ScenesManifest(
        video_id="sha",
        source_topology=topology,  # type: ignore[arg-type]
        resolution={"w": width, "h": height},
        fps_num=30,
        fps_den=1,
        scenes=[
            scene("SC_0001", 0.0, 8.0, "TALKING_HEAD", ["SAFE_FOR_BROLL"]),
            scene("SC_0002", 8.0, 20.0, "SCREEN_SHARE_PIP", ["PROTECT_FROM_BROLL"]),
            scene("SC_0003", 20.0, 30.0, "TALKING_HEAD", ["SAFE_FOR_BROLL"]),
        ],
    )


def _plan(manifest: ScenesManifest | None = None, *, start: float = 0.0, end: float = 30.0):
    manifest = manifest or _manifest()
    draft = deterministic_draft(
        manifest, short_id="SH", start_sec=start, end_sec=end
    )
    return resolve_draft(draft, manifest).plan, manifest


def test_segment_renders_follow_layout_panels() -> None:
    plan, manifest = _plan()
    renders = build_segment_renders(plan, manifest)
    assert [item.layout for item in renders] == [
        "FULL_FACE",
        "SPLIT_SCREEN_SAFE",
        "FULL_FACE",
    ]
    assert renders[0].face_crop.width == round(1080 * 0.5625)
    assert renders[1].screen_crop is not None
    assert renders[1].screen_crop.height == 1080
    assert renders[1].screen_crop.width == 1389
    assert renders[2].face_crop.height == 1080


def test_smooth_track_splits_at_scene_boundaries() -> None:
    plan, manifest = _plan()
    wide = plan.model_copy(
        update={
            "segments": [
                plan.segments[0].model_copy(
                    update={
                        "seg_id": "S1",
                        "rel_start": 0.0,
                        "rel_end": 30.0,
                        "layout": "FULL_FACE",
                    }
                )
            ]
        }
    )
    renders = build_segment_renders(wide, manifest, smooth_track=True)
    assert len(renders) == 3
    assert renders[0].source_end == 8.0
    assert renders[1].source_start == 8.0
    assert renders[2].source_end == 30.0


def test_dual_canvas_offsets_camera_and_screen() -> None:
    manifest = _manifest(3840, 1080, "dual_canvas")
    plan, _ = _plan(manifest)
    renders = build_segment_renders(plan, manifest, cam_side="right")
    screen = next(item for item in renders if item.screen_crop is not None)
    assert screen.screen_crop is not None
    assert screen.screen_crop.x < 1920
    assert screen.screen_crop.right <= 1920
    assert screen.face_crop.x >= 1920


def test_segment_filters_cover_layouts() -> None:
    plan, manifest = _plan()
    renders = build_segment_renders(plan, manifest)
    full = segment_filter(renders[0], fps=30)
    assert "crop=" in full
    assert "scale=1080:1920" in full
    assert "fps=30" in full
    assert "[0:a]asetpts" in full

    split = segment_filter(renders[1], fps=30)
    assert "vstack=inputs=2" in split
    assert "pad=1080:1920" in split
    assert "split=2" in split

    broll = SegmentRender(
        seg_id="B",
        source_start=0.0,
        source_end=5.0,
        layout="SPLIT_BROLL",
        face_crop=renders[0].face_crop,
        broll_path=Path("/tmp/broll.mp4"),
    )
    graph = segment_filter(broll, fps=30)
    assert "[1:v]" in graph
    assert "drawbox" in graph


def test_commands_build_tokens_and_final_audio() -> None:
    plan, manifest = _plan()
    renders = build_segment_renders(plan, manifest)
    commands = build_commands(
        renders,
        source=Path("/media/source.mp4"),
        captions=Path("/tmp/captions.ass"),
        sfx=[SfxRenderCue(Path("/tmp/whoosh.wav"), 7.9, -18.0)],
        output_name="short.mp4",
        encoder="nvenc",
        fade_start=30.27,
        fade_ms=80,
        padding_sec=0.35,
        fontsdir="/home/u/.videoflow/assets/fonts",
    )
    assert len(commands.segments) == 3
    assert commands.concat_names[0] == "seg_0001.mp4"
    first = commands.segments[0]
    assert "-filter_complex_script" in first["argv"]
    assert "__SCRIPT_1__" in first["argv"]
    assert commands.final_filter.count("ass=") == 1
    assert "fontsdir='/home/u/.videoflow/assets/fonts'" in commands.final_filter
    assert "tpad=stop_mode=clone:stop_duration=0.350" in commands.final_filter
    assert "apad=pad_dur=0.350" in commands.final_filter
    assert "loudnorm=I=-14:TP=-1.5:LRA=9" in commands.final_filter
    assert "adelay=7900|7900" in commands.final_filter
    assert "[a0][s1]amix=inputs=2" in commands.final_filter
    assert "h264_nvenc" in commands.final_argv
    assert commands.final_argv[-1] == "short.mp4"


class _FakeRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.scripts: dict[Path, str] = {}

    def __call__(self, argv: list[str], cwd: Path) -> None:
        self.calls.append(list(argv))
        if "-filter_complex_script" in argv:
            script = Path(argv[argv.index("-filter_complex_script") + 1])
            self.scripts[script] = script.read_text(encoding="utf-8")
        output = Path(argv[-1])
        if not output.is_absolute():
            output = cwd / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"mp4")


def test_execute_commands_substitutes_tokens(tmp_path: Path) -> None:
    plan, manifest = _plan()
    renders = build_segment_renders(plan, manifest)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"src")
    captions = tmp_path / "captions.ass"
    captions.write_text("[Script Info]\n", encoding="utf-8")
    commands = build_commands(
        renders,
        source=source,
        captions=captions,
        output_name="short.mp4",
        fade_start=30.27,
        padding_sec=0.35,
    )
    runner = _FakeRunner()
    output = execute_commands(commands, tmp_path / "work", runner=runner)
    assert output.is_file()
    assert len(runner.calls) == 4  # 3 segments + final
    assert all("__IN" not in item for call in runner.calls for item in call)
    assert all("__SCRIPT" not in item for call in runner.calls for item in call)
    assert all("__IN" not in text for text in runner.scripts.values())
    concat = (tmp_path / "work" / "concat.txt").read_text(encoding="utf-8")
    assert concat.count("file '") == 3
    assert (tmp_path / "work" / "final.ffscript").is_file()


def test_execute_commands_raises_without_output(tmp_path: Path) -> None:
    plan, manifest = _plan()
    commands = build_commands(
        build_segment_renders(plan, manifest),
        source=tmp_path / "source.mp4",
    )

    def no_output(argv: list[str], cwd: Path) -> None:
        return None

    with pytest.raises(IngestError, match="produced no output"):
        execute_commands(commands, tmp_path / "work", runner=no_output)


def test_nvenc_detection_handles_missing_binary() -> None:
    assert nvenc_available("/definitely/not/ffmpeg") is False


def test_worker_short_render_executes_tokenised_commands(
    tmp_path: Path, monkeypatch
) -> None:
    import sys

    package_src = (
        Path(__file__).resolve().parents[2] / "packages" / "gpu-worker" / "src"
    )
    if str(package_src) not in sys.path:
        sys.path.insert(0, str(package_src))
    from gpu_worker import handlers_gpu
    from gpu_worker.gpu_handlers import render as render_handlers
    from gpu_worker.settings import Settings

    plan, manifest = _plan()
    renders = build_segment_renders(plan, manifest)
    source = tmp_path / "source.mp4"
    captions = tmp_path / "captions.ass"
    source.write_bytes(b"source")
    captions.write_text("[Script Info]\n", encoding="utf-8")
    font = tmp_path / "Inter.ttf"
    font.write_bytes(b"font")
    commands = build_commands(
        renders,
        source=source,
        captions=captions,
        output_name="short.mp4",
    )
    calls: list[list[str]] = []

    def fake_run(argv: list[str], cwd: Path, *, timeout: float = 3600.0) -> None:
        calls.append(list(argv))
        output = Path(argv[-1])
        if not output.is_absolute():
            output = Path(cwd) / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"mp4")

    monkeypatch.setattr(render_handlers, "_run_in", fake_run)
    handler = handlers_gpu.make_short_render_handler(
        Settings(work_dir=tmp_path / "worker")
    )
    payload = commands.to_payload()
    payload["font_paths"] = [str(font)]
    outputs = handler(
        payload,
        [source, captions],
        tmp_path / "job",
    )
    assert outputs[0].name == "short.mp4"
    assert len(calls) == len(commands.segments) + 1
    assert all("__IN" not in item for call in calls for item in call)
    assert all("__SCRIPT" not in item for call in calls for item in call)
    scripts = list((tmp_path / "job").glob("*.ffscript"))
    assert scripts
    script_text = "\n".join(script.read_text(encoding="utf-8") for script in scripts)
    assert "__IN" not in script_text
    assert "fontsdir=" in script_text
    assert (tmp_path / "job" / "concat.txt").is_file()


def _render_context(tmp_path: Path):
    from videoflow.application.short_composition.captions import (
        CaptionBlock,
        build_short_ass,
    )
    from videoflow.core.context import PipelineContext
    from videoflow.domain.short_composition import ShortCompositionPlan, ShortSegment

    manifest = _manifest()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    plan = ShortCompositionPlan(
        short_id="SH",
        source_video_path=str(source),
        start=0.0,
        end=30.0,
        segments=[
            ShortSegment(seg_id="S1", rel_start=0.0, rel_end=30.0, layout="FULL_FACE")
        ],
    )
    output = tmp_path / "out"
    captions = output / "shorts" / "SH" / "captions.ass"
    captions.parent.mkdir(parents=True)
    captions.write_text(
        build_short_ass([CaptionBlock(0.5, 2.0, ("hello",), subtitle_y=1360)]),
        encoding="utf-8",
    )
    context = PipelineContext(
        source=source,
        output=output,
        work=tmp_path / "work",
        exports=tmp_path / "exports",
    )
    context.metadata["short_plan"] = plan.model_dump(mode="json")
    context.metadata["scenes_manifest"] = manifest.model_dump(mode="json")
    context.metadata["short_cues"] = {
        "ending": {
            "content_end_sec": 30.0,
            "effective_end_sec": 30.35,
            "fade_out_ms": 80,
        },
        "sfx": [],
    }
    context.artifacts["short_captions"] = str(captions)
    return context, plan


def test_short_render_remote_only_requires_worker(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    from videoflow import application as application_module
    from videoflow.domain.errors import IngestError
    from videoflow.mcp_server.context import error  # noqa: F401 - import order
    from videoflow.steps import short_render as step_module

    context, _plan = _render_context(tmp_path)

    class Router:
        def decide(self, capability: str):
            return SimpleNamespace(is_remote=False, reason="worker offline")

    monkeypatch.setattr(
        application_module.compute, "router_from_settings", lambda: Router()
    )
    with pytest.raises(IngestError, match="worker offline"):
        step_module.ShortRenderStep().run(
            context,
            step_module.ShortRenderParams(compute_policy="remote_only"),
            StepIO(),
        )


def test_short_render_remote_success_records_placement(
    tmp_path: Path, monkeypatch
) -> None:
    from types import SimpleNamespace

    from videoflow import application as application_module
    from videoflow.steps import short_render as step_module
    from videoflow.steps.base import StepIO

    context, _plan = _render_context(tmp_path)
    downloaded = tmp_path / "downloaded.mp4"
    downloaded.write_bytes(b"mp4")
    submitted: dict[str, object] = {}

    class Router:
        def decide(self, capability: str):
            return SimpleNamespace(is_remote=True, reason="", execution_node="remote_gpu")

        def health(self):
            return SimpleNamespace(nvenc=True, available=True)

        def submit(self, capability, payload, *, timeout):
            submitted["capability"] = capability
            submitted["payload"] = payload
            return {"path": str(downloaded)}

    class Probe:
        width = 1080
        height = 1920

    monkeypatch.setattr(
        application_module.compute, "router_from_settings", lambda: Router()
    )
    monkeypatch.setattr(
        step_module,
        "FFmpegAdapter",
        lambda: SimpleNamespace(probe=lambda path: Probe()),
    )
    step_module.ShortRenderStep().run(
        context,
        step_module.ShortRenderParams(
            compute_policy="remote_only",
            encoder="auto",
        ),
        StepIO(),
    )
    assert submitted["capability"] == "short_render"
    payload = submitted["payload"]
    assert payload["params"]["output_name"] == "short.mp4"
    assert any(token == "ffmpeg" for token in [payload["params"]["final_argv"][0]])
    assert context.metadata["short_render"]["placement"] == "remote_gpu"
    assert Path(context.artifacts["short_render"]).is_file()


def test_safe_output_name_strips_paths() -> None:
    from videoflow.application.short_composition.render import safe_output_name

    assert safe_output_name("../../escape.mp4", default="short.mp4", suffix=".mp4") == "escape.mp4"
    assert safe_output_name("clip", default="short.mp4", suffix=".mp4") == "clip.mp4"
    assert safe_output_name("", default="short.mp4", suffix=".mp4") == "short.mp4"


def test_commands_add_silence_for_video_without_audio(tmp_path: Path) -> None:
    plan, manifest = _plan()
    renders = build_segment_renders(plan, manifest)
    silent = [
        SegmentRender(
            seg_id=renders[0].seg_id,
            source_start=renders[0].source_start,
            source_end=renders[0].source_end,
            layout=renders[0].layout,
            face_crop=renders[0].face_crop,
            has_audio=False,
        )
    ]
    commands = build_commands(silent, source=tmp_path / "source.mp4")
    argv = commands.segments[0]["argv"]
    assert "anullsrc=r=48000:cl=stereo" in argv
    assert "[1:a]asetpts" in str(commands.segments[0]["filter"])


def test_segment_cache_reuses_micro_clips(tmp_path: Path) -> None:
    plan, manifest = _plan()
    renders = build_segment_renders(plan, manifest)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    commands = build_commands(renders, source=source, output_name="short.mp4")
    cache = tmp_path / "cache"

    class Runner:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, argv: list[str], cwd: Path) -> None:
            self.calls += 1
            output = Path(argv[-1])
            if not output.is_absolute():
                output = cwd / output
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"mp4")

    first = Runner()
    execute_commands(commands, tmp_path / "work1", runner=first, segment_cache=cache)
    second = Runner()
    execute_commands(commands, tmp_path / "work2", runner=second, segment_cache=cache)
    assert first.calls == len(commands.segments) + 1
    assert second.calls == 1  # only the final concat/encode
    assert len(list(cache.glob("*.mp4"))) == len(commands.segments)
