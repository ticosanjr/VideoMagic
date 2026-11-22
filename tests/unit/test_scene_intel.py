from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application.scene_intel import detect as detect_module
from videoflow.application.scene_intel import keyframes as keyframes_module
from videoflow.application.scene_intel import pipeline as pipeline_module
from videoflow.application.scene_intel.detect import (
    DetectionResult,
    SceneSpan,
    detect_scene_spans,
)
from videoflow.application.scene_intel.keyframes import extract_scene_keyframes
from videoflow.application.scene_intel.layout import editing_hints
from videoflow.application.scene_intel.manifest import build_manifest
from videoflow.application.scene_intel.supercontext import (
    build_supercontext,
    planner_payload,
)
from videoflow.application.scene_intel.visual import SceneVisual, classify_layout
from videoflow.domain.state import MediaInfo


def _media(width: int = 1920, height: int = 1080) -> MediaInfo:
    return MediaInfo(
        source_path="source.mp4",
        duration_frames=600,
        fps_num=30,
        fps_den=1,
        width=width,
        height=height,
        audio_sample_rate=48_000,
    )


def _visual(**overrides: object) -> SceneVisual:
    payload = {
        "face_count": 1,
        "face_cx": 0.5,
        "face_cy": 0.4,
        "face_w": 0.2,
        "face_h": 0.3,
        "face_area_ratio": 0.06,
        "edge_density": 0.02,
        "sharpness_laplacian": 200.0,
        "sampled_frames": 4,
    }
    payload.update(overrides)
    return SceneVisual(**payload)  # type: ignore[arg-type]


def test_detect_scene_spans_fuses_decupage_jumps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(detect_module, "_py_scene_detect", lambda *a, **k: [3.0, 8.0])
    plan = {
        "sample_rate": 1000,
        "cuts": [
            {"start_sample": 5000, "end_sample": 10000},
        ],
    }
    result = detect_scene_spans(
        Path("source.mp4"),
        Path("proxy.mp4"),
        fps=30.0,
        duration=20.0,
        decupage_plan=plan,
    )
    assert result.engine == "pyscenedetect"
    boundaries = [(item.start_sec, item.end_sec) for item in result.spans]
    assert boundaries[0] == (0.0, 3.0)
    assert (5.0, 8.0) in boundaries
    assert result.spans[-1].end_sec == 20.0
    assert any(item.transition_source == "DECUPAGEM_JUMP" for item in result.spans)


def test_detect_scene_spans_falls_back_to_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> list[float]:
        raise ImportError("scenedetect missing")

    monkeypatch.setattr(detect_module, "_py_scene_detect", boom)
    monkeypatch.setattr(detect_module, "_ffmpeg_detect", lambda *a, **k: [4.0])
    result = detect_scene_spans(
        Path("source.mp4"),
        Path("proxy.mp4"),
        fps=30.0,
        duration=12.0,
    )
    assert result.engine == "ffmpeg_fallback"
    assert result.warnings
    assert [item.start_sec for item in result.spans] == [0.0, 4.0]


def test_layout_classification_order() -> None:
    media = _media()
    assert classify_layout(_visual(), media, "single_16x9") == "TALKING_HEAD"
    assert (
        classify_layout(_visual(face_area_ratio=0.01), media, "single_16x9")
        == "SCREEN_SHARE_PIP"
    )
    assert (
        classify_layout(
            _visual(face_count=0, face_area_ratio=0.0, edge_density=0.12),
            media,
            "single_16x9",
        )
        == "SCREEN_SHARE_FULL"
    )
    assert (
        classify_layout(
            _visual(face_count=0, face_area_ratio=0.0, edge_density=0.01),
            media,
            "single_16x9",
        )
        == "BROLL_OR_FOOTAGE"
    )
    assert classify_layout(_visual(), _media(3840, 1080), "auto") == "DUAL_CANVAS_OBS"


def test_editing_hints_are_deterministic() -> None:
    hints = editing_hints(
        layout="TALKING_HEAD",
        duration_sec=13.0,
        edge_density=0.02,
        sharpness_laplacian=30.0,
        previous_layout="SCREEN_SHARE_FULL",
    )
    assert "LONG_STATIC_SHOT" in hints
    assert "SCENE_TYPE_SWITCH" in hints
    assert "LOW_SHARPNESS_WARNING" in hints
    assert "SAFE_FOR_BROLL" in hints
    screen = editing_hints(
        layout="SCREEN_SHARE_FULL",
        duration_sec=5.0,
        edge_density=0.2,
        sharpness_laplacian=200.0,
        previous_layout="SCREEN_SHARE_FULL",
    )
    assert "PROTECT_FROM_BROLL" in screen
    assert editing_hints(
        layout="DUAL_CANVAS_OBS",
        duration_sec=5.0,
        edge_density=0.0,
        sharpness_laplacian=200.0,
        previous_layout=None,
    ) == ["DUAL_CANVAS_READY"]


def test_manifest_and_supercontext_round_trip() -> None:
    spans = [SceneSpan(0.0, 13.0), SceneSpan(13.0, 20.0, "DECUPAGEM_JUMP")]
    visuals = [_visual(), _visual(face_count=0, face_area_ratio=0.0, edge_density=0.2)]
    build = build_manifest(
        video_id="sha",
        media=_media(),
        spans=spans,
        visuals=visuals,
        topology="single_16x9",
        keyframe_paths=["/tmp/SC_0001.jpg", "/tmp/SC_0002.jpg"],
        engine="pyscenedetect",
    )
    manifest = build.manifest
    assert [scene.scene_id for scene in manifest.scenes] == ["SC_0001", "SC_0002"]
    assert manifest.scenes[0].layout_type == "TALKING_HEAD"
    assert "LONG_STATIC_SHOT" in manifest.scenes[0].editing_hints
    assert manifest.scenes[1].layout_type == "SCREEN_SHARE_FULL"
    assert manifest.scenes[1].transition_source == "DECUPAGEM_JUMP"

    context = build_supercontext(
        manifest,
        asus=[{"asu_id": "A1", "start_sec": 1.0, "end_sec": 3.0, "text": "hello"}],
        decupage_plan={
            "sample_rate": 1000,
            "cuts": [{"start_sample": 1000, "end_sample": 2000}],
        },
    )
    assert context["asus"][0]["scene_id"] == "SC_0001"
    assert context["asus"][0]["broll_allowed"] is True
    assert context["cut_spans"][0]["start_sec"] == 1.0

    payload = planner_payload(context)
    assert "start_sec" not in payload["asus"][0]
    assert payload["asus"][0]["asu_id"] == "A1"


def test_protected_scene_blocks_broll() -> None:
    manifest = build_manifest(
        video_id="sha",
        media=_media(),
        spans=[SceneSpan(0.0, 10.0)],
        visuals=[_visual(face_count=0, face_area_ratio=0.0, edge_density=0.3)],
        topology="single_16x9",
        keyframe_paths=[""],
        engine="pyscenedetect",
    ).manifest
    context = build_supercontext(
        manifest,
        asus=[{"asu_id": "A1", "start_sec": 1.0, "end_sec": 2.0, "text": "x"}],
    )
    assert context["asus"][0]["protected_from_broll"] is True
    assert context["asus"][0]["broll_allowed"] is False


def test_pipeline_cache_reuses_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    calls = {"detect": 0}

    monkeypatch.setattr(pipeline_module, "file_sha256", lambda path: "sha-test")
    monkeypatch.setattr(
        pipeline_module,
        "ensure_proxy",
        lambda source, media, workspace, force=False: (workspace.proxy, True),
    )

    def fake_detect(*args: object, **kwargs: object) -> DetectionResult:
        calls["detect"] += 1
        return DetectionResult((SceneSpan(0.0, 10.0),), "pyscenedetect")

    monkeypatch.setattr(pipeline_module, "detect_scene_spans", fake_detect)
    monkeypatch.setattr(
        pipeline_module,
        "analyze_visuals",
        lambda *a, **k: ([_visual()], []),
    )
    monkeypatch.setattr(
        pipeline_module,
        "attach_keyframes",
        lambda *a, **k: ([""], []),
    )

    first = pipeline_module.analyze_scene_project(
        source,
        tmp_path / "scenes",
        media=_media(),
    )
    assert first.cache_hit is False
    assert calls["detect"] == 1
    assert first.workspace.manifest.is_file()
    assert first.workspace.supercontext.is_file()

    second = pipeline_module.analyze_scene_project(
        source,
        tmp_path / "scenes",
        media=_media(),
    )
    assert second.cache_hit is True
    assert calls["detect"] == 1
    assert second.manifest.scenes[0].scene_id == "SC_0001"

    third = pipeline_module.analyze_scene_project(
        source,
        tmp_path / "scenes",
        media=_media(),
        threshold=4.0,
    )
    assert third.cache_hit is False
    assert calls["detect"] == 2


def test_keyframes_are_reused_and_failures_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeAdapter:
        def __init__(self) -> None:
            self.calls: list[Path] = []

        def extract_keyframe(
            self,
            source: Path,
            destination: Path,
            *,
            time_sec: float,
            max_size: int,
            quality: int,
        ) -> Path:
            self.calls.append(destination)
            if "SC_0002" in destination.name:
                raise RuntimeError("decode failed")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"jpg")
            return destination

    adapter = FakeAdapter()
    monkeypatch.setattr(keyframes_module, "FFmpegAdapter", lambda: adapter)
    spans = [SceneSpan(0.0, 4.0), SceneSpan(4.0, 8.0)]
    paths, warnings = extract_scene_keyframes(
        tmp_path / "source.mp4",
        spans,
        tmp_path / "keyframes",
        scene_ids=["SC_0001", "SC_0002"],
    )
    assert Path(paths[0]).is_file()
    assert paths[1] == ""
    assert warnings and "SC_0002" in warnings[0]

    reused, _ = extract_scene_keyframes(
        tmp_path / "source.mp4",
        spans,
        tmp_path / "keyframes",
        scene_ids=["SC_0001", "SC_0002"],
    )
    assert reused[0] == paths[0]
    assert len(adapter.calls) == 3  # SC_0002 retried because it has no file


def test_scene_analyze_step_records_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.core.context import PipelineContext
    from videoflow.steps import scene_analyze as step_module
    from videoflow.steps.base import StepIO

    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    context = PipelineContext(
        source=source,
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
    )
    reachable = _media()
    monkeypatch.setattr(step_module, "require_media", lambda ctx: reachable)
    monkeypatch.setattr(step_module, "file_sha256", lambda path: "sha-step")
    monkeypatch.setattr(pipeline_module, "file_sha256", lambda path: "sha-step")
    monkeypatch.setattr(step_module, "load_scene_cache", lambda *a, **k: None)
    monkeypatch.setattr(
        pipeline_module,
        "ensure_proxy",
        lambda source, media, workspace, force=False: (workspace.proxy, True),
    )
    monkeypatch.setattr(
        pipeline_module,
        "detect_scene_spans",
        lambda *a, **k: DetectionResult((SceneSpan(0.0, 10.0),), "pyscenedetect"),
    )
    monkeypatch.setattr(
        pipeline_module, "analyze_visuals", lambda *a, **k: ([_visual()], [])
    )
    monkeypatch.setattr(pipeline_module, "attach_keyframes", lambda *a, **k: ([""], []))

    step_module.SceneAnalyzeStep().run(
        context,
        step_module.SceneAnalyzeParams(force=True, compute_policy="local"),
        StepIO(),
    )
    assert context.metadata["scenes_manifest"]["scenes"][0]["scene_id"] == "SC_0001"
    assert context.metadata["scenes_summary"]["scene_count"] == 1
    assert context.metadata["scenes_compute"]["placement"] == "local"
    assert context.metadata["scenes_compute"]["degraded"] is False
    assert context.metadata["scenes_supercontext"]["scenes"]
    assert Path(context.artifacts["scenes_manifest"]).is_file()
    assert "scene.analyze" in context.cache_misses


def test_remote_scene_analysis_materializes_keyframes(
    tmp_path: Path,
) -> None:
    import json
    import zipfile

    from videoflow.application.scene_intel.proxy import scene_workspace
    from videoflow.application.scene_intel.remote import analyze_scene_remote
    from videoflow.domain.errors import VideoFlowError

    workspace = scene_workspace(tmp_path / "scenes", "sha-remote")
    workspace.root.mkdir(parents=True, exist_ok=True)
    manifest_payload = {
        "schema_version": 1,
        "video_id": "sha-remote",
        "source_topology": "single_16x9",
        "resolution": {"w": 1920, "h": 1080},
        "fps_num": 30,
        "fps_den": 1,
        "scenes": [
            {
                "scene_id": "SC_0001",
                "start_sample": 0,
                "end_sample": 48_000,
                "start_sec": 0.0,
                "end_sec": 1.0,
                "layout_type": "TALKING_HEAD",
                "face_count": 1,
                "face_bbox_norm": {"cx": 0.5, "cy": 0.4, "w": 0.2, "h": 0.3},
                "face_area_ratio": 0.06,
                "edge_density": 0.01,
                "sharpness_laplacian": 120.0,
                "keyframe_path": "keyframes/SC_0001.jpg",
            }
        ],
    }
    manifest_path = tmp_path / "scenes_manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")
    archive = tmp_path / "scene_keyframes.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("keyframes/SC_0001.jpg", b"jpg")

    captured: dict[str, object] = {}

    class Router:
        def submit(self, capability: str, payload: dict, *, timeout: float) -> dict:
            captured["capability"] = capability
            captured["payload"] = payload
            return {"paths": [str(manifest_path), str(archive)], "elapsed_sec": 1.5}

    result = analyze_scene_remote(
        Router(),
        tmp_path / "source.mp4",
        workspace,
        _media(),
        threshold=3.0,
        min_scene_len_sec=1.5,
        source_topology="single_16x9",
        keyframe_size=544,
        video_id="sha-remote",
    )
    assert captured["capability"] == "scene_analyze"
    assert result.manifest.scenes[0].keyframe_path == str(
        workspace.keyframes / "SC_0001.jpg"
    )
    assert Path(result.manifest.scenes[0].keyframe_path).is_file()
    assert result.workspace.manifest.is_file()
    assert result.workspace.supercontext.is_file()

    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as bundle:
        bundle.writestr("../evil.jpg", b"x")

    class UnsafeRouter:
        def submit(self, capability: str, payload: dict, *, timeout: float) -> dict:
            return {"paths": [str(manifest_path), str(unsafe)]}

    with pytest.raises(VideoFlowError):
        analyze_scene_remote(
            UnsafeRouter(),
            tmp_path / "source.mp4",
            scene_workspace(tmp_path / "other", "sha-remote"),
            _media(),
            threshold=3.0,
            min_scene_len_sec=1.5,
            source_topology="single_16x9",
            keyframe_size=544,
            video_id="sha-remote",
        )


def test_scene_step_offloads_to_remote_router(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow import application as application_module
    from videoflow.application.scene_intel.pipeline import SceneAnalysisResult
    from videoflow.application.scene_intel.proxy import scene_workspace
    from videoflow.core.context import PipelineContext
    from videoflow.domain.scenes import SceneEntry, ScenesManifest
    from videoflow.steps import scene_analyze as step_module
    from videoflow.steps.base import StepIO

    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    context = PipelineContext(
        source=source,
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
    )
    workspace = scene_workspace(tmp_path / "out" / "scenes", "sha-remote")
    manifest = ScenesManifest(
        video_id="sha-remote",
        resolution={"w": 1920, "h": 1080},
        fps_num=30,
        fps_den=1,
        scenes=[
            SceneEntry(
                scene_id="SC_0001",
                start_sample=0,
                end_sample=48_000,
                start_sec=0.0,
                end_sec=1.0,
                layout_type="TALKING_HEAD",
            )
        ],
    )
    remote_result = SceneAnalysisResult(
        manifest=manifest,
        workspace=workspace,
        supercontext={"scenes": [], "asus": []},
        video_id="sha-remote",
        cache_key="key",
        engine="remote_scene_analyze",
        cache_hit=False,
        elapsed_sec=0.4,
    )

    class Router:
        def __init__(self) -> None:
            self.capability = ""

        def execute(self, capability, remote_fn, local_fn, **kwargs):
            self.capability = capability
            return {
                "value": remote_fn(),
                "execution_node": "remote_gpu",
                "degraded": False,
                "degraded_reason": "",
            }

    router = Router()
    monkeypatch.setattr(
        application_module.compute, "router_from_settings", lambda: router
    )
    monkeypatch.setattr(step_module, "require_media", lambda ctx: _media())
    monkeypatch.setattr(step_module, "file_sha256", lambda path: "sha-remote")
    monkeypatch.setattr(step_module, "load_scene_cache", lambda *a, **k: None)
    monkeypatch.setattr(step_module, "analyze_scene_remote", lambda *a, **k: remote_result)

    def local_must_not_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("local scene analysis should not run")

    monkeypatch.setattr(step_module, "analyze_scene_project", local_must_not_run)
    step_module.SceneAnalyzeStep().run(
        context,
        step_module.SceneAnalyzeParams(compute_policy="auto"),
        StepIO(),
    )
    assert router.capability == "scene_analyze"
    assert context.metadata["scenes_compute"]["placement"] == "remote_gpu"
    assert context.metadata["scenes_compute"]["degraded"] is False


def test_detect_merges_micro_scenes_without_gaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(detect_module, "_py_scene_detect", lambda *a, **k: [1.0, 6.0])
    result = detect_scene_spans(
        Path("source.mp4"),
        Path("proxy.mp4"),
        fps=30.0,
        duration=10.0,
        min_scene_len_sec=1.5,
    )
    spans = [(item.start_sec, item.end_sec) for item in result.spans]
    assert spans == [(0.0, 6.0), (6.0, 10.0)]
    assert result.spans[0].start_sec == 0.0
    assert result.spans[-1].end_sec == 10.0


def test_scene_workspace_rejects_path_traversal(tmp_path: Path) -> None:
    from videoflow.application.scene_intel.proxy import scene_workspace

    with pytest.raises(ValueError):
        scene_workspace(tmp_path, "../../etc")
    with pytest.raises(ValueError):
        scene_workspace(tmp_path, "..")
    assert scene_workspace(tmp_path, "sha-abc_123").root.name == "sha-abc_123"
