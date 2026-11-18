from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from videoflow.application.captions import caption_lines
from videoflow.application.curation import (
    _contact_sheet,
    build_minute_sample,
    build_music_candidates,
)
from videoflow.application.media_integrity import probe_media, validate_integrity
from videoflow.application.qa_final import audit_final
from videoflow.application.release_kit import _thumbnails
from videoflow.application.shorts_batch import run_shorts_batch
from videoflow.domain.config import CaptionStyle
from videoflow.domain.errors import ExportError
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    OverlayClip,
    ProjectState,
    Sentence,
    VideoSegment,
    WordTiming,
)


def _media(tmp_path: Path, *, width: int = 640, height: int = 360) -> MediaInfo:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    return MediaInfo(
        source_path=str(source),
        duration_frames=90,
        fps_num=30,
        fps_den=1,
        width=width,
        height=height,
        audio_sample_rate=48000,
    )


def _state(tmp_path: Path) -> ProjectState:
    media = _media(tmp_path)
    return ProjectState(
        media_info=media,
        sources={"primary": media},
        primary_source_id="primary",
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_id="primary",
                source_in_frame=0,
                source_out_frame=90,
                timeline_in_frame=0,
                timeline_out_frame=90,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_id="primary",
                source_in_sample=0,
                source_out_sample=144000,
                timeline_in_sample=0,
                timeline_out_sample=144000,
            )
        ],
    )


def _tools(tmp_path: Path, monkeypatch):
    from videoflow.application.jobs import JobManager
    from videoflow.application.projects import init_project, save_project_state
    from videoflow.engine.batch import BatchManager
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    record, _ = init_project(name="Tools", output=tmp_path / "tools")
    save_project_state(record, _state(tmp_path), bump_revision=False)
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager, batch_manager=BatchManager(manager)),
    )
    return tools, record, manager


def test_new_mcp_tools_error_paths(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = _tools(tmp_path, monkeypatch)
    for name, args in (
        ("vf_overlay_preview", {"project_id": "missing"}),
        ("vf_layout", {"project_id": "missing"}),
        ("vf_caption_preview", {"project_id": "missing"}),
        ("vf_qa_autofix", {"project_id": "missing"}),
        ("vf_shorts_batch", {"project_id": "missing", "clips": []}),
        ("vf_qa_final", {"project_id": "missing"}),
    ):
        assert tools[name](**args)["ok"] is False
    assert (
        tools["vf_export"](
            project_id=record.project_id, audio_source="invalid"
        )["ok"]
        is False
    )
    assert tools["vf_font"](action="bogus")["ok"] is False
    assert tools["vf_font"](action="install")["ok"] is False
    assert (
        tools["vf_overlay"](
            project_id=record.project_id,
            asset_path=str(tmp_path / "missing.png"),
        )["ok"]
        is False
    )


def test_job_heartbeat_and_shorts_batch_success(tmp_path: Path, monkeypatch) -> None:
    tools, record, manager = _tools(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "videoflow.application.shorts_batch.run_shorts_batch",
        lambda *args, **kwargs: {"ok": True, "clips": []},
    )
    batch = tools["vf_shorts_batch"](project_id=record.project_id, clips=[])
    waited = tools["vf_job"](
        action="wait",
        project_id=record.project_id,
        job_id=batch["job"]["job_id"],
        timeout_sec=10,
    )
    assert waited["ok"] is True
    job = manager.get(batch["job"]["job_id"])
    heartbeat = manager.heartbeat(str(job.job_id))
    assert heartbeat.job_id == job.job_id


def test_shorts_batch_missing_media(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application.projects import init_project

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home2"))
    record, _ = init_project(name="No media", output=tmp_path / "no-media")
    with pytest.raises(ExportError):
        run_shorts_batch(record.project_id, [{"start_sec": 0, "end_sec": 1}])


def test_mp4_overlay_branches(tmp_path: Path, monkeypatch) -> None:
    from videoflow.exporters import mp4

    media = _media(tmp_path)
    state = ProjectState(
        media_info=media,
        sources={"primary": media},
        primary_source_id="primary",
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_id="primary",
                source_in_frame=0,
                source_out_frame=90,
                timeline_in_frame=0,
                timeline_out_frame=90,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_id="primary",
                source_in_sample=0,
                source_out_sample=144000,
                timeline_in_sample=0,
                timeline_out_sample=144000,
            )
        ],
        overlays=[
            OverlayClip(
                overlay_id="video",
                path=str(tmp_path / "overlay.mp4"),
                start_frame=0,
                duration_frames=30,
                anchor="top_center",
                kind="video",
                ken_burns=True,
                transformative_crop=True,
                transition_in="fade",
                transition_out="fade",
                z=50,
            ),
            OverlayClip(
                overlay_id="missing",
                path=str(tmp_path / "missing.png"),
                start_frame=0,
                duration_frames=30,
                z=10,
            ),
        ],
    )
    (tmp_path / "overlay.mp4").write_bytes(b"v")
    ass = tmp_path / "captions.ass"
    ass.write_text("[Script Info]\n", encoding="utf-8")
    calls: list[list[str]] = []

    class FakeRenderer:
        def render(self, args):
            calls.append(list(args))
            Path(args[-1]).write_bytes(b"mp4")

    monkeypatch.setattr(mp4, "_duration_gate_enabled", lambda adapter: False)
    monkeypatch.setattr(
        "videoflow.application.overlay_geometry.asset_dimensions",
        lambda *args, **kwargs: (100, 50),
    )
    mp4.export_mp4(state, tmp_path / "out.mp4", adapter=FakeRenderer(), ass_path=ass)
    graph = calls[0][calls[0].index("-filter_complex") + 1]
    assert "zoompan" in graph and "colorchannelmixer" in graph
    assert "overlay=" in graph


def test_qa_final_caption_and_unavailable_backends(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import qa_final

    video = tmp_path / "master.mp4"
    video.write_bytes(b"v")
    state = _state(tmp_path)
    state.transcript = [Sentence(id=0, start_sample=0, end_sample=1000, text="hello")]
    captions = Path(tmp_path) / "captions" / "captions.ass"
    captions.parent.mkdir(parents=True)
    captions.write_text("[Script Info]\n", encoding="utf-8")
    class Integrity:
        ok = True

        def to_dict(self):
            return {"ok": True}

    monkeypatch.setattr(qa_final, "validate_integrity", lambda *a, **k: Integrity())
    monkeypatch.setattr(qa_final, "detect_black", lambda path: [])
    monkeypatch.setattr(qa_final, "detect_freeze", lambda path: [])
    monkeypatch.setattr(
        qa_final,
        "detect_audio_silence",
        lambda path: [{"duration_sec": 1.0, "severity": "warning"}],
    )
    monkeypatch.setattr(qa_final, "render_waveform", lambda *a, **k: None)
    monkeypatch.setattr(
        "videoflow.adapters.ffmpeg.FFmpegAdapter.measure_loudness",
        lambda self, path: {"integrated_lufs": -20.0, "true_peak_dbfs": 0.0},
    )
    report = audit_final(video, output=tmp_path, state=state, strict=True)
    assert report["status"] == "needs_review"
    assert any(item["kind"] == "audio_silence" for item in report["issues"])
    assert report["caption_qa"]["skipped"] is False


def test_media_integrity_edges(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import media_integrity as integrity

    payload = {
        "format": {"duration": "2.0"},
        "streams": [
            {"codec_type": "video", "duration": "2.0", "nb_read_frames": "60"},
            {"codec_type": "audio", "duration": None},
        ],
    }
    monkeypatch.setattr(integrity, "probe_media", lambda path: payload)
    report = validate_integrity(
        tmp_path / "x.mp4",
        2.0,
        expected_frames=60,
        fps=30,
        last_sentence_end_sec=2.5,
    )
    assert report.ok is False
    assert "last sentence" in report.reason
    assert report.frame_delta == 0
    monkeypatch.setattr(
        integrity.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="bad", stdout=""),
    )
    with pytest.raises(ExportError):
        probe_media(tmp_path / "x.mp4")
    monkeypatch.setattr(
        integrity.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr="", stdout="not-json"),
    )
    with pytest.raises(ExportError):
        probe_media(tmp_path / "x.mp4")


def test_caption_lines_fallback_and_static() -> None:
    sentence = Sentence(
        id=0,
        start_sample=0,
        end_sample=48000,
        text="one two three four five six seven eight",
        words=[
            WordTiming(
                word=word,
                start_sample=index * 2000,
                end_sample=(index + 1) * 2000,
                probability=0.9,
            )
            for index, word in enumerate(
                ["one", "two", "three", "four", "five", "six", "seven", "eight"]
            )
        ],
    )
    lines = caption_lines([sentence], [(0, 48000)], sample_rate=48000, max_words=4)
    assert len(lines) >= 2
    no_words = caption_lines(
        [sentence.model_copy(update={"words": []})],
        [(0, 48000)],
        sample_rate=48000,
        word_timing="word",
    )
    assert no_words
    style = CaptionStyle(effect="static")
    from videoflow.application.captions import build_ass_lines

    text = build_ass_lines(no_words, style=style, width=320, height=240)
    assert "\\k" not in text


def test_curation_branches(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import curation
    from videoflow.application.projects import init_project, save_project_state
    from videoflow.domain.errors import ExportError

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home3"))
    record, _ = init_project(name="Curation", output=tmp_path / "curation")
    state = _state(tmp_path)
    save_project_state(record, state, bump_revision=False)
    monkeypatch.setattr(
        curation,
        "_ffmpeg",
        lambda: (_ for _ in ()).throw(ExportError("no ffmpeg")),
    )
    with pytest.raises(ExportError):
        build_music_candidates(record.project_id)
    with pytest.raises(ExportError):
        build_minute_sample(record.project_id)
    assert _contact_sheet([], tmp_path / "none.jpg") is None
    monkeypatch.setattr(curation, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        curation,
        "compose_music",
        lambda directory, **kwargs: {"files": {"mix": str(Path(directory) / "x.wav")}},
    )
    monkeypatch.setattr(
        curation.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="bad", stdout=""),
    )
    with pytest.raises(ExportError):
        build_music_candidates(record.project_id)

    def fake_ok(command, **kwargs):
        target = Path(command[-1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"wav")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(curation.subprocess, "run", fake_ok)
    candidates = build_music_candidates(record.project_id)
    assert len(candidates) == 3


def test_release_kit_thumbnails(tmp_path: Path, monkeypatch) -> None:
    state = _state(tmp_path)
    source = tmp_path / "thumb-source.jpg"
    Image.new("RGB", (320, 180), "red").save(source)
    state.media_info = state.media_info.model_copy(update={"source_path": str(source)})
    monkeypatch.setattr(
        "videoflow.application.release_kit.FFmpegAdapter.render_thumbnail",
        lambda self, source, target, **kwargs: Path(target).write_bytes(b"jpg") or target,
    )
    items = _thumbnails(tmp_path, state, "Title", tmp_path)
    assert len(items) == 2


def test_caption_qa_static_and_escape(tmp_path: Path) -> None:
    from videoflow.application.qa_caption import audit_ass

    assert audit_ass(tmp_path / "missing.ass")["ok"] is False
    path = tmp_path / "static.ass"
    path.write_text(
        "[Events]\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,plain text\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\kf0}bad\n"
        "Dialogue: 0,0:00:02.00,0:00:03.00,Default,,0,0,0,,{\\\\c&H00FF00&}double\n",
        encoding="utf-8",
    )
    report = audit_ass(path, effect="karaoke_sweep", max_chars=4)
    kinds = {item["kind"] for item in report["issues"]}
    assert {"caption_effect", "caption_zero_duration", "caption_escape", "caption_width"} <= kinds


def test_preview_error_paths(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import caption_preview, overlay_preview

    state = _state(tmp_path)
    with pytest.raises(ExportError):
        caption_preview.render_caption_preview(
            ProjectState(), tmp_path, time_sec=0.0
        )
    missing = state.model_copy(
        update={
            "media_info": state.media_info.model_copy(
                update={"source_path": str(tmp_path / "missing.mp4")}
            )
        }
    )
    with pytest.raises(ExportError):
        caption_preview.render_caption_preview(missing, tmp_path, time_sec=0.0)
    with pytest.raises(ExportError):
        overlay_preview.render_overlay_preview(ProjectState(), tmp_path)
    with pytest.raises(ExportError):
        overlay_preview.render_overlay_preview(missing, tmp_path)
    monkeypatch.setattr(
        "videoflow.application.caption_preview.find_binary", lambda name: None
    )
    with pytest.raises(ExportError):
        caption_preview.render_caption_preview(state, tmp_path, time_sec=0.0)
    monkeypatch.setattr(
        "videoflow.application.overlay_preview.find_binary", lambda name: None
    )
    with pytest.raises(ExportError):
        overlay_preview.render_overlay_preview(state, tmp_path)
    monkeypatch.setattr(
        "videoflow.application.caption_preview.find_binary", lambda name: "ffmpeg"
    )
    monkeypatch.setattr(
        "videoflow.application.overlay_preview.find_binary", lambda name: "ffmpeg"
    )
    monkeypatch.setattr(
        "videoflow.application.caption_preview.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=1, stderr="bad", stdout=""),
    )
    state.transcript = [Sentence(id=0, start_sample=0, end_sample=1000, text="hello")]
    with pytest.raises(ExportError):
        caption_preview.render_caption_preview(state, tmp_path, time_sec=0.0)
    monkeypatch.setattr(
        "videoflow.application.overlay_preview.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=1, stderr="bad", stdout=""),
    )
    with pytest.raises(ExportError):
        overlay_preview.render_overlay_preview(state, tmp_path)


def test_layout_autopack_changes(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import layout
    from videoflow.application.projects import init_project, save_project_state

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home4"))
    record, _ = init_project(name="Layout", output=tmp_path / "layout")
    state = _state(tmp_path)
    image = tmp_path / "low.png"
    Image.new("RGB", (100, 50), "red").save(image)
    state.overlays = [
        OverlayClip(
            overlay_id="low",
            path=str(image),
            start_frame=0,
            duration_frames=30,
            anchor="bottom_left",
            width_ratio=0.5,
        )
    ]
    save_project_state(record, state, bump_revision=False)
    result = layout.pack_project_layout(record.project_id, apply=True)
    assert result["layout"]["overlays"]


def test_core_tool_exception_branches(tmp_path: Path, monkeypatch) -> None:
    tools, record, _ = _tools(tmp_path, monkeypatch)
    for name, target in (
        ("vf_overlay_preview", "videoflow.application.overlay_preview.render_overlay_preview"),
        ("vf_layout", "videoflow.application.layout.pack_project_layout"),
        ("vf_caption_preview", "videoflow.application.caption_preview.render_caption_preview"),
        ("vf_qa_autofix", "videoflow.application.layout.pack_project_layout"),
    ):
        monkeypatch.setattr(target, lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
        assert tools[name](project_id=record.project_id)["ok"] is False
    assert tools["vf_export"](project_id="missing")["ok"] is False
    assert tools["vf_exports"](action="validate", project_id="missing")["ok"] is False
    assert tools["vf_job"](action="wait", project_id="missing", job_id="x")["ok"] is False


def test_release_kit_missing_source_and_thumbnail_error(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import release_kit
    from videoflow.application.projects import init_project, save_project_state

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home5"))
    record, _ = init_project(name="Kit2", output=tmp_path / "kit2")
    state = _state(tmp_path)
    save_project_state(record, state, bump_revision=False)
    assert release_kit._thumbnails(tmp_path, ProjectState(), "T", tmp_path) == []
    missing = state.model_copy(
        update={
            "media_info": state.media_info.model_copy(
                update={"source_path": str(tmp_path / "missing.mp4")}
            )
        }
    )
    assert release_kit._thumbnails(tmp_path, missing, "T", tmp_path) == []
    monkeypatch.setattr(
        "videoflow.application.release_kit.FFmpegAdapter.render_thumbnail",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad")),
    )
    assert release_kit._thumbnails(tmp_path, state, "T", tmp_path) == []


def test_core_tool_misc_branches(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import style_service

    tools, record, _ = _tools(tmp_path, monkeypatch)
    assert tools["vf_style"](action="learn_rule")["ok"] is False
    assert tools["vf_style"](action="bogus")["ok"] is False
    monkeypatch.setattr(
        style_service,
        "list_styles",
        lambda: (_ for _ in ()).throw(ValueError("bad style")),
    )
    assert tools["vf_style"](action="list")["ok"] is False
    assert tools["vf_project"](action="archive", project_id="missing")["ok"] is False
    assert tools["vf_project"](action="clone", project_id="missing")["ok"] is False
    assert tools["vf_project"](action="list", status="active")["projects"]
    assert tools["vf_exec"](action="step", project_id="missing")["ok"] is False
    assert tools["vf_run"](project_id=record.project_id, steps=["no-such-step"])["ok"] is False
    assert tools["vf_jobs"](action="cancel", job_id="missing")["ok"] is False
    assert tools["vf_jobs"](action="bogus", job_id="x")["ok"] is False
    assert (
        tools["vf_timeline"](
            action="apply_beatmap",
            project_id=record.project_id,
            keep_ranges=[{"start_sec": 1.0, "end_sec": 0.5}],
        )["ok"]
        is False
    )
    assert (
        tools["vf_timeline"](
            action="edit",
            project_id=record.project_id,
            time_basis="source",
            start_sec=99.0,
        )["ok"]
        is False
    )
    assert tools["vf_exports"](action="bundle", project_id="missing")["ok"] is False
    assert tools["vf_interaction"](action="list", job_id="missing")["ok"] is False
    assert tools["vf_ingest"](action="session", project_id="missing")["ok"] is False


def test_curation_step_interactive(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application.projects import init_project, save_project_state
    from videoflow.core.context import PipelineContext
    from videoflow.domain.errors import HumanInputRequiredError
    from videoflow.domain.hilt import HiltRequest
    from videoflow.steps.base import StepIO
    from videoflow.steps.curation import CurationParams, CurationPrepareStep

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home6"))
    record, _ = init_project(name="Interactive", output=tmp_path / "interactive")
    state = _state(tmp_path)
    save_project_state(record, state, bump_revision=False)
    context = PipelineContext(
        source=Path(state.media_info.source_path),
        output=Path(record.output),
        work=Path(record.output) / "work",
        exports=Path(record.output) / "exports",
        media=state.media_info,
        state=state,
        metadata={"project_id": record.project_id, "job_id": "job"},
    )
    payload = {
        "path": str(tmp_path / "curation.json"),
        "music": [{"id": "M1", "preview": ""}],
        "broll": {"candidates": [{"id": "A", "path": ""}]},
        "sample": {"path": ""},
    }
    monkeypatch.setattr(
        "videoflow.steps.curation.curation_manifest", lambda project_id: payload
    )
    request = HiltRequest(
        interaction_id="hilt-curation-gate",
        gate_id="curation",
        title="Curation",
        questions=[{"id": "music", "label": "Music", "type": "choice", "options": ["M1"]}],
    )
    monkeypatch.setattr(
        "videoflow.steps.curation.hilt.create_request",
        lambda *args, **kwargs: (request, "token"),
    )
    monkeypatch.setattr(
        "videoflow.steps.curation.hilt.load_response", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "videoflow.application.hilt_channels.notify_request", lambda *args, **kwargs: None
    )
    with pytest.raises(HumanInputRequiredError):
        CurationPrepareStep().run(
            context, CurationParams(interactive=True), StepIO()
        )


def test_curation_and_integrity_remaining_branches(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import curation
    from videoflow.application import media_integrity as integrity
    from videoflow.application.projects import init_project, save_project_state

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home7"))
    record, _ = init_project(name="Remaining", output=tmp_path / "remaining")
    state = _state(tmp_path)
    save_project_state(record, state, bump_revision=False)
    monkeypatch.setattr(curation, "find_binary", lambda name: None)
    with pytest.raises(ExportError):
        curation._ffmpeg()
    master = Path(record.output) / "audio" / "master.wav"
    master.parent.mkdir(parents=True)
    master.write_bytes(b"wav")
    assert curation._voice(record.project_id) == master
    monkeypatch.setattr(
        curation, "_voice", lambda project_id: None
    )
    monkeypatch.setattr(
        curation,
        "compose_music",
        lambda directory, **kwargs: {"files": {"mix": str(Path(directory) / "x.wav")}},
    )
    assert build_music_candidates(record.project_id)[0]["preview"].endswith("x.wav")
    empty = state.model_copy(update={"media_info": None})
    save_project_state(record, empty, bump_revision=True)
    with pytest.raises(ExportError):
        curation.build_broll_contact_sheet(record.project_id)
    with pytest.raises(ExportError):
        build_minute_sample(record.project_id)
    save_project_state(record, ProjectState(), bump_revision=True)
    with pytest.raises(ExportError):
        curation.build_broll_contact_sheet(record.project_id)
    with pytest.raises(ExportError):
        build_minute_sample(record.project_id)
    save_project_state(record, state, bump_revision=True)
    missing = state.model_copy(
        update={
            "media_info": state.media_info.model_copy(
                update={"source_path": str(tmp_path / "missing.mp4")}
            )
        }
    )
    save_project_state(record, missing, bump_revision=True)
    with pytest.raises(ExportError):
        curation.build_broll_contact_sheet(record.project_id)
    monkeypatch.setattr(curation, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        curation.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="bad", stdout=""),
    )
    with pytest.raises(ExportError):
        build_minute_sample(record.project_id)

    assert integrity._seconds("bad") is None
    monkeypatch.setattr(
        integrity,
        "probe_media",
        lambda path: {
            "format": {"duration": "1.0"},
            "streams": [{"codec_type": "video", "duration": "1.0", "nb_read_frames": "30"}],
        },
    )
    report = integrity.validate_integrity(
        tmp_path / "x.mp4",
        1.0,
        expected_frames=30,
        fps=30,
        last_sentence_end_sec=2.0,
    )
    assert report.ok is False
    with pytest.raises(ExportError):
        integrity.validate_or_raise(tmp_path / "x.mp4", 2.0)


def test_geometry_layout_and_caption_remaining(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import layout, overlay_geometry, qa_caption
    from videoflow.application.projects import init_project, save_project_state

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home8"))
    record, _ = init_project(name="No media", output=tmp_path / "no-media-layout")
    save_project_state(record, ProjectState(), bump_revision=False)
    with pytest.raises(ExportError):
        layout.pack_project_layout(record.project_id)
    # video dimensions through ffprobe
    monkeypatch.setattr(
        overlay_geometry.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stderr="", stdout='{"streams":[{"width":200,"height":100}]}'
        ),
    )
    assert overlay_geometry.asset_dimensions(tmp_path / "clip.mp4", "video") == (200, 100)
    monkeypatch.setattr(
        overlay_geometry.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr="", stdout="bad"),
    )
    assert overlay_geometry.asset_dimensions(tmp_path / "clip.mp4", "video") == (1, 1)
    state = _state(tmp_path)
    image = tmp_path / "a.png"
    Image.new("RGB", (100, 50), "red").save(image)
    state.overlays = [
        OverlayClip(
            overlay_id="top",
            path=str(image),
            start_frame=0,
            duration_frames=30,
            anchor="top_left",
            width_ratio=0.2,
        ),
        OverlayClip(
            overlay_id="bottom",
            path=str(image),
            start_frame=0,
            duration_frames=30,
            anchor="bottom_left",
            width_ratio=0.2,
        ),
    ]
    caption = overlay_geometry.caption_box(CaptionStyle(), 640, 360)
    assert overlay_geometry.auto_pack(state, 640, 360, caption=caption)
    path = tmp_path / "empty.ass"
    path.write_text("[Events]\n", encoding="utf-8")
    assert qa_caption.audit_ass(path, effect="static")["ok"] is True


def test_small_remaining_branches(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import brand_kit, qa_caption
    from videoflow.application.shorts_tighten import passes_metrics, tighten_clip

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home9"))
    root = brand_kit.brand_kit_root("chan2")
    root.mkdir(parents=True)
    (root / "nested").mkdir()
    (root / "music.wav").write_bytes(b"m")
    (root / "vignette.wav").write_bytes(b"s")
    kit = brand_kit.load_brand_kit("chan2")
    assert kit["music"] and kit["sting"]
    path = tmp_path / "malformed.ass"
    path.write_text("Dialogue: broken\n", encoding="utf-8")
    assert qa_caption.audit_ass(path, effect="static")["ok"] is True
    empty = tighten_clip(
        start_sample=0,
        end_sample=1000,
        speech_intervals=[],
        words=[],
        sample_rate=48000,
    )
    assert empty.pieces == ((0, 1000),)
    assert passes_metrics({"speech_ratio": 0.1}) is False


def test_step_guard_branches(tmp_path: Path) -> None:
    from videoflow.core.context import PipelineContext
    from videoflow.steps.base import StepIO
    from videoflow.steps.qa_final import FinalQaParams, FinalQaStep
    from videoflow.steps.release_kit import ReleaseKitParams, ReleaseKitStep
    from videoflow.steps.transcript_dedupe import DedupeParams, TranscriptDedupeStep

    context = PipelineContext(
        source=tmp_path / "s.mp4",
        output=tmp_path,
        work=tmp_path / "w",
        exports=tmp_path / "e",
    )
    with pytest.raises(ExportError):
        FinalQaStep().run(context, FinalQaParams(), StepIO())
    context.state = _state(tmp_path)
    with pytest.raises(ExportError):
        FinalQaStep().run(
            context,
            FinalQaParams(video_path=str(tmp_path / "missing.mp4")),
            StepIO(),
        )
    ReleaseKitStep().run(context, ReleaseKitParams(), StepIO())
    context.media = _state(tmp_path).media_info
    TranscriptDedupeStep().run(context, DedupeParams(), StepIO())


def test_last_three_coverage_statements(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import curation, overlay_geometry
    from videoflow.application.projects import init_project, save_project_state

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home10"))
    record, _ = init_project(name="No media voice", output=tmp_path / "voice")
    save_project_state(record, ProjectState(), bump_revision=False)
    assert curation._voice(record.project_id) is None
    monkeypatch.setattr(overlay_geometry, "find_binary", lambda name: None)
    assert overlay_geometry.asset_dimensions(tmp_path / "clip.mp4", "video") == (1, 1)
    state = _state(tmp_path)
    image = tmp_path / "b.png"
    Image.new("RGB", (100, 50), "blue").save(image)
    state.overlays = [
        OverlayClip(
            overlay_id="left",
            path=str(image),
            start_frame=0,
            duration_frames=10,
            anchor="top_left",
            width_ratio=0.1,
        ),
        OverlayClip(
            overlay_id="right",
            path=str(image),
            start_frame=20,
            duration_frames=10,
            anchor="bottom_right",
            width_ratio=0.1,
        ),
    ]
    assert overlay_geometry.collisions(state, 640, 360) == []
    assert overlay_geometry.auto_pack(state, 640, 360, caption=None) == []


def test_overlay_bounds_step_and_nle_geometry(tmp_path: Path) -> None:
    import xml.etree.ElementTree as ET

    from tests.contract.test_exporters import sample_state
    from videoflow.core.context import PipelineContext
    from videoflow.exporters.extras import NleBroll, NleExtras
    from videoflow.exporters.fcpxml import export_fcpxml
    from videoflow.exporters.kdenlive import export_kdenlive
    from videoflow.exporters.xmeml import export_xmeml
    from videoflow.steps.base import StepIO
    from videoflow.steps.qa_overlay_bounds import OverlayBoundsParams, OverlayBoundsStep

    state = _state(tmp_path)
    image = tmp_path / "nle.png"
    Image.new("RGB", (100, 50), "red").save(image)
    state.overlays = [
        OverlayClip(
            overlay_id="nle",
            path=str(image),
            start_frame=0,
            duration_frames=30,
            anchor="top_center",
            width_ratio=0.2,
            z=30,
        )
    ]
    context = PipelineContext(
        source=Path(state.media_info.source_path),
        output=tmp_path / "bounds",
        work=tmp_path / "bounds" / "work",
        exports=tmp_path / "bounds" / "exports",
        media=state.media_info,
        state=state,
    )
    OverlayBoundsStep().run(context, OverlayBoundsParams(strict=False), StepIO())
    assert context.artifacts["overlay_bounds"]

    base = sample_state(tmp_path)
    extras = NleExtras(
        broll=(
            NleBroll(
                path=str(image),
                start_sec=0.0,
                duration_sec=1.0,
                anchor="top_center",
                width_ratio=0.2,
                z=50,
                x=100,
                y=0,
                width=128,
                height=72,
                source_width=100,
                source_height=50,
            ),
        )
    )
    fcpxml = export_fcpxml(base, tmp_path / "t.fcpxml", extras=extras)
    assert ET.parse(fcpxml).getroot().find(".//asset-clip/adjust-transform") is not None
    xmeml = export_xmeml(base, tmp_path / "t.xml", extras=extras)
    assert (
        ET.parse(xmeml)
        .getroot()
        .find(".//clipitem/filter/effect[name='Basic Motion']")
        is not None
    )
    kdenlive = export_kdenlive(base, tmp_path / "t.kdenlive", extras=extras)
    assert "rect" in kdenlive.read_text(encoding="utf-8")


def test_layout_autofix_rerender_branch(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import layout
    from videoflow.application.projects import init_project, save_project_state

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home11"))
    record, _ = init_project(name="Autofix", output=tmp_path / "autofix")
    state = _state(tmp_path)
    image = tmp_path / "low2.png"
    Image.new("RGB", (100, 50), "red").save(image)
    state.overlays = [
        OverlayClip(
            overlay_id="low",
            path=str(image),
            start_frame=0,
            duration_frames=30,
            anchor="bottom_left",
            width_ratio=0.5,
        )
    ]
    save_project_state(record, state, bump_revision=False)
    monkeypatch.setattr(
        "videoflow.application.layout.render_master",
        lambda state, destination, **kwargs: (
            Path(destination).parent.mkdir(parents=True, exist_ok=True)
            or Path(destination).write_bytes(b"mp4")
            or destination
        ),
    )
    monkeypatch.setattr(
        "videoflow.application.qa_final.audit_final",
        lambda *args, **kwargs: {"ok": True, "status": "succeeded"},
    )
    result = layout.pack_project_layout(
        record.project_id,
        apply=True,
        rerender=True,
    )
    assert result["rerendered"]["ok"] is True


def test_sfx_demo_mixes_cues(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import curation
    from videoflow.application.curation import build_sfx_demo
    from videoflow.application.projects import init_project, save_project_state

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home12"))
    record, _ = init_project(name="SFX", output=tmp_path / "sfx")
    save_project_state(record, _state(tmp_path), bump_revision=False)
    monkeypatch.setattr(curation, "_ffmpeg", lambda: "ffmpeg")

    def fake_foley(directory, cues, **kwargs):
        Path(directory).mkdir(parents=True, exist_ok=True)
        written = []
        for index, cue in enumerate(cues, start=1):
            path = Path(directory) / f"{index:03d}-{cue['kind']}.wav"
            path.write_bytes(b"wav")
            written.append({"path": str(path), "kind": cue["kind"]})
        return {"cues": written, "count": len(written)}

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"demo")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(curation, "synthesize_foley", fake_foley)
    monkeypatch.setattr(curation.subprocess, "run", fake_run)
    result = build_sfx_demo(record.project_id)
    assert result["ok"] is True
    assert Path(result["preview"]).name == "sfx-demo-10s.wav"
    assert result["duration_sec"] == 10.0
    monkeypatch.setattr(
        curation.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="bad", stdout=""),
    )
    failed = build_sfx_demo(record.project_id)
    assert Path(failed["preview"]).name != "sfx-demo-10s.wav"


def test_qa_steps_skip_and_strict(tmp_path: Path) -> None:
    from videoflow.core.context import PipelineContext
    from videoflow.domain.errors import RecipeError, StateNotReadyError
    from videoflow.steps.base import StepIO
    from videoflow.steps.qa_caption import CaptionEffectParams, CaptionEffectStep
    from videoflow.steps.qa_overlay_bounds import OverlayBoundsParams, OverlayBoundsStep

    context = PipelineContext(
        source=tmp_path / "s.mp4",
        output=tmp_path / "out",
        work=tmp_path / "out" / "work",
        exports=tmp_path / "out" / "exports",
    )
    with pytest.raises(StateNotReadyError):
        OverlayBoundsStep().run(context, OverlayBoundsParams(), StepIO())
    context.media = _state(tmp_path).media_info
    caption_dir = context.output / "captions"
    caption_dir.mkdir(parents=True)
    (caption_dir / "captions.ass").write_text(
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,plain\n",
        encoding="utf-8",
    )
    CaptionEffectStep().run(
        context,
        CaptionEffectParams(effect="karaoke_sweep", strict=False),
        StepIO(),
    )
    assert context.metadata["caption_effect"]["ok"] is False
    context.state = _state(tmp_path)
    context.state.overlays = [
        OverlayClip(
            overlay_id="edge",
            path=str(tmp_path / "edge.png"),
            start_frame=0,
            duration_frames=30,
            anchor="bottom_right",
            width_ratio=0.5,
        )
    ]
    Image.new("RGB", (100, 50), "red").save(tmp_path / "edge.png")
    with pytest.raises(RecipeError):
        OverlayBoundsStep().run(
            context,
            OverlayBoundsParams(strict=True, platforms=["shorts"]),
            StepIO(),
        )


def test_minute_sample_prefers_delivered_master(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import curation
    from videoflow.application.projects import init_project, save_project_state

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home13"))
    record, _ = init_project(name="Sample", output=tmp_path / "sample")
    save_project_state(record, _state(tmp_path), bump_revision=False)
    delivered = Path(record.output) / "exports" / "youtube_master.mp4"
    delivered.parent.mkdir(parents=True)
    delivered.write_bytes(b"master")
    monkeypatch.setattr(curation, "_ffmpeg", lambda: "ffmpeg")

    def fake_run(command, **kwargs):
        target = Path(command[-1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"sample")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(curation.subprocess, "run", fake_run)
    result = build_minute_sample(record.project_id)
    assert result["ok"] is True
    assert Path(result["path"]).is_file()


def test_layout_partial_and_qa_fallbacks(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import caption_preview, layout
    from videoflow.application.projects import init_project, save_project_state
    from videoflow.core.context import PipelineContext
    from videoflow.steps.base import StepIO
    from videoflow.steps.qa_caption import CaptionEffectParams, CaptionEffectStep
    from videoflow.steps.qa_overlay_bounds import OverlayBoundsParams, OverlayBoundsStep

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home14"))
    record, _ = init_project(name="Partial", output=tmp_path / "partial")
    state = _state(tmp_path)
    image = tmp_path / "partial.png"
    Image.new("RGB", (100, 50), "red").save(image)
    state.overlays = [
        OverlayClip(
            overlay_id="collides",
            path=str(image),
            start_frame=0,
            duration_frames=30,
            anchor="bottom_left",
            width_ratio=0.5,
        ),
        OverlayClip(
            overlay_id="clear",
            path=str(image),
            start_frame=0,
            duration_frames=30,
            anchor="top_left",
            width_ratio=0.1,
        ),
    ]
    save_project_state(record, state, bump_revision=False)
    result = layout.pack_project_layout(record.project_id, apply=True)
    assert result["layout"]["overlays"]

    context = PipelineContext(
        source=Path(state.media_info.source_path),
        output=tmp_path / "qa-fallback",
        work=tmp_path / "qa-fallback" / "work",
        exports=tmp_path / "qa-fallback" / "exports",
        media=state.media_info,
        state=state,
    )
    CaptionEffectStep().run(context, CaptionEffectParams(strict=False), StepIO())
    assert context.metadata["caption_effect"]["skipped"] is True
    OverlayBoundsStep().run(context, OverlayBoundsParams(strict=False), StepIO())
    with pytest.raises(ExportError):
        caption_preview.render_caption_preview(state, tmp_path, time_sec=0.0)


def test_overlay_preview_safe_zone_failure(tmp_path: Path, monkeypatch) -> None:
    import sys
    from types import ModuleType

    from videoflow.application import overlay_preview

    state = _state(tmp_path)
    state.overlays = [
        OverlayClip(
            overlay_id="o",
            path=str(tmp_path / "missing.png"),
            start_frame=0,
            duration_frames=10,
        )
    ]

    def fake_run(command, **kwargs):
        target = Path(command[-1])
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (640, 360), "red").save(target, format="JPEG")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(overlay_preview.subprocess, "run", fake_run)
    broken = ModuleType("videoflow.steps.qa_safezone")

    def _raise(name):
        raise RuntimeError("broken safe zones")

    broken.__getattr__ = _raise  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "videoflow.steps.qa_safezone", broken)
    result = overlay_preview.render_overlay_preview(state, tmp_path)
    assert result["ok"] is True


def test_word_fidelity_backend_error(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application.qa_word_fidelity import verify_word_fidelity
    from videoflow.domain.state import Sentence

    monkeypatch.setattr(
        "videoflow.adapters.faster_whisper.FasterWhisperAdapter.available",
        staticmethod(lambda *args, **kwargs: True),
    )
    monkeypatch.setattr(
        "videoflow.adapters.ffmpeg.FFmpegAdapter.extract_pcm",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("bad backend")),
    )
    result = verify_word_fidelity(
        tmp_path / "x.mp4",
        [Sentence(id=0, start_sample=0, end_sample=1, text="hello")],
        work=tmp_path,
    )
    assert result["status"] == "unavailable"
    assert result["passed"] is True


def test_minute_sample_failure_branch(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import curation
    from videoflow.application.projects import init_project, save_project_state

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home15"))
    record, _ = init_project(name="Sample fail", output=tmp_path / "sample-fail")
    state = _state(tmp_path)
    save_project_state(record, state, bump_revision=False)
    monkeypatch.setattr(curation, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        curation.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="bad", stdout=""),
    )
    with pytest.raises(ExportError):
        build_minute_sample(record.project_id)
