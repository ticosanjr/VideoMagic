from __future__ import annotations

from pathlib import Path

from videoflow.application import qa_final
from videoflow.application.media_integrity import IntegrityReport
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    OverlayClip,
    ProjectState,
    Sentence,
    VideoSegment,
)


def _state(tmp_path: Path) -> ProjectState:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    return ProjectState(
        media_info=MediaInfo(
            source_path=str(source),
            duration_frames=1800,
            fps_num=30,
            fps_den=1,
            width=1920,
            height=1080,
            audio_sample_rate=48000,
        ),
        transcript=[Sentence(id=0, start_sample=0, end_sample=48000, text="texto")],
        language="pt",
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_in_frame=0,
                source_out_frame=1800,
                timeline_in_frame=0,
                timeline_out_frame=1800,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="a1",
                source_in_sample=0,
                source_out_sample=2_880_000,
                timeline_in_sample=0,
                timeline_out_sample=2_880_000,
            )
        ],
    )


def _patch(monkeypatch, *, wer: float = 0.04) -> list[str]:
    calls: list[str] = []

    def integrity(*args, **kwargs):
        calls.append("integrity")
        return IntegrityReport(ok=True, expected_sec=60.0)

    def fidelity(*args, **kwargs):
        calls.append("fidelity")
        return {"status": "checked", "passed": wer < kwargs.get("max_wer", 0.12), "wer": wer}

    monkeypatch.setattr(qa_final, "validate_integrity", integrity)
    monkeypatch.setattr(qa_final, "detect_audio_silence", lambda *a, **k: [])
    monkeypatch.setattr(qa_final, "detect_black", lambda *a, **k: [])
    monkeypatch.setattr(qa_final, "detect_freeze", lambda *a, **k: [])
    monkeypatch.setattr(qa_final, "verify_word_fidelity", fidelity)
    monkeypatch.setattr(qa_final, "_contact_sheet", lambda *a, **k: None)
    monkeypatch.setattr(qa_final, "render_waveform", lambda *a, **k: None)
    from videoflow.adapters.ffmpeg import FFmpegAdapter

    monkeypatch.setattr(
        FFmpegAdapter,
        "measure_loudness",
        lambda self, path: {
            "integrated_lufs": -16.0,
            "true_peak_dbfs": -1.5,
        },
    )
    return calls


def test_fast_mode_skips_expensive_full_checks(
    tmp_path: Path, monkeypatch
) -> None:
    video = tmp_path / "deliverable.mp4"
    video.write_bytes(b"mp4")
    calls = _patch(monkeypatch)
    monkeypatch.setattr(
        qa_final,
        "verify_word_fidelity",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("fast mode called WER")),
    )
    report = qa_final.audit_final(
        video,
        output=tmp_path,
        state=_state(tmp_path),
        mode="fast",
    )
    assert report["mode"] == "fast"
    assert report["word_fidelity"]["skipped"] is True
    assert report["caption_qa"]["skipped"] is True
    assert report["loudness"]["skipped"] is False
    assert report["loudness"]["passed"] is True
    assert "fidelity" not in calls


def test_fast_mode_ignores_intentional_top_chrome_overlay(
    tmp_path: Path, monkeypatch
) -> None:
    from PIL import Image

    video = tmp_path / "deliverable.mp4"
    video.write_bytes(b"mp4")
    image = tmp_path / "top.png"
    Image.new("RGBA", (100, 100), (255, 0, 0, 255)).save(image)
    state = _state(tmp_path)
    state.overlays.append(
        OverlayClip(
            overlay_id="top-chrome",
            path=str(image),
            start_frame=0,
            duration_frames=1800,
            anchor="top_center",
            margin_y=0,
            width_ratio=0.5,
        )
    )
    _patch(monkeypatch)
    report = qa_final.audit_final(
        video,
        output=tmp_path,
        state=state,
        mode="fast",
        platforms=["shorts"],
        width=1080,
        height=1920,
    )
    assert not any(
        item.get("kind") == "safe_zone"
        and item.get("overlay_id") == "top-chrome"
        for item in report["issues"]
    )


def test_fast_mode_still_checks_caption_syntax(tmp_path: Path, monkeypatch) -> None:
    video = tmp_path / "deliverable.mp4"
    video.write_bytes(b"mp4")
    captions = tmp_path / "captions.ass"
    captions.write_text(
        "[Events]\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,"
        "literal \\c&H00FF00& text\n",
        encoding="utf-8",
    )
    _patch(monkeypatch)
    report = qa_final.audit_final(
        video,
        output=tmp_path,
        state=_state(tmp_path),
        mode="fast",
        width=320,
        height=240,
        caption_path=captions,
    )
    assert report["caption_qa"]["skipped"] is False
    assert any(item["kind"] == "caption_escape" for item in report["issues"])


def test_full_mode_reports_wer_warning_and_critical(
    tmp_path: Path, monkeypatch
) -> None:
    video = tmp_path / "deliverable.mp4"
    video.write_bytes(b"mp4")
    state = _state(tmp_path)
    _patch(monkeypatch, wer=0.08)
    warning = qa_final.audit_final(
        video,
        output=tmp_path,
        state=state,
        mode="full",
        max_wer=0.12,
        warning_wer=0.06,
    )
    assert warning["ok"] is True
    assert any(item["kind"] == "word_fidelity" for item in warning["issues"])

    _patch(monkeypatch, wer=0.2)
    critical = qa_final.audit_final(
        video,
        output=tmp_path,
        state=state,
        mode="full",
        max_wer=0.12,
        warning_wer=0.06,
    )
    assert critical["ok"] is False
    assert any(
        item["kind"] == "word_fidelity" and item["severity"] == "critical"
        for item in critical["issues"]
    )


def test_short_aware_audit_uses_the_clip_window(
    tmp_path: Path, monkeypatch
) -> None:
    video = tmp_path / "short.mp4"
    video.write_bytes(b"mp4")
    _patch(monkeypatch, wer=0.04)
    report = qa_final.audit_final(
        video,
        output=tmp_path,
        state=_state(tmp_path),
        mode="fast",
        window_sec=(10.0, 40.0),
        expected_sec=30.0,
        fps=30.0,
        width=1080,
        height=1920,
        transcript=[Sentence(id=0, start_sample=480000, end_sample=1920000, text="short")],
    )
    assert report["window_sec"] == [10.0, 40.0]
    assert report["expected_sec"] == 30.0
    assert report["expected_frames"] == 900
    assert report["expected_samples"] == 1_440_000
    assert report["fps"] == 30.0


def test_fast_mode_with_window_derives_expected_duration(tmp_path: Path, monkeypatch) -> None:
    video = tmp_path / "short.mp4"
    video.write_bytes(b"mp4")
    _patch(monkeypatch, wer=0.04)
    report = qa_final.audit_final(
        video,
        output=tmp_path,
        state=_state(tmp_path),
        mode="fast",
        window_sec=(10.0, 40.0),
        fps=30.0,
        width=1080,
        height=1920,
    )
    assert report["expected_sec"] == 30.0
    assert report["expected_frames"] == 900


def test_invalid_mode_fails_loudly(tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"mp4")
    import pytest

    with pytest.raises(ValueError, match="mode must be"):
        qa_final.audit_final(
            video,
            output=tmp_path,
            state=_state(tmp_path),
            mode="bogus",
        )


def test_full_mode_classifies_edge_and_internal_silence(tmp_path: Path, monkeypatch) -> None:
    video = tmp_path / "deliverable.mp4"
    video.write_bytes(b"mp4")
    _patch(monkeypatch, wer=0.04)
    monkeypatch.setattr(
        qa_final,
        "detect_audio_silence",
        lambda *a, **k: [
            {"start_sec": 0.0, "end_sec": 0.4, "duration_sec": 0.4},
            {"start_sec": 59.5, "end_sec": 60.0, "duration_sec": 0.5},
            {"start_sec": 20.0, "end_sec": 21.0, "duration_sec": 1.0},
        ],
    )
    report = qa_final.audit_final(
        video,
        output=tmp_path,
        state=_state(tmp_path),
        mode="full",
        expected_sec=60.0,
    )
    messages = [item.get("message", "") for item in report["issues"]]
    assert any("Initial edge" in message for message in messages)
    assert any("Final edge" in message for message in messages)
    assert any("Internal dead air" in message for message in messages)


def test_full_mode_checks_caption_tags_and_visual_collisions(
    tmp_path: Path, monkeypatch
) -> None:
    from PIL import Image

    video = tmp_path / "deliverable.mp4"
    video.write_bytes(b"mp4")
    image = tmp_path / "overlay.png"
    Image.new("RGBA", (100, 100), (255, 0, 0, 255)).save(image)
    state = _state(tmp_path)
    state.overlays.append(
        OverlayClip(
            overlay_id="card",
            path=str(image),
            start_frame=0,
            duration_frames=1800,
            anchor="top_left",
            width_ratio=0.5,
        )
    )
    modules = state.modules_config.model_copy(deep=True)
    modules.shorts.caption_style.position_y = 0.10
    state = state.model_copy(update={"modules_config": modules})
    captions = tmp_path / "captions.ass"
    captions.write_text(
        "[Events]\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,"
        "literal \\c&H00FF00& text\n",
        encoding="utf-8",
    )
    _patch(monkeypatch, wer=0.04)
    report = qa_final.audit_final(
        video,
        output=tmp_path,
        state=state,
        mode="full",
        width=320,
        height=240,
        caption_path=captions,
    )
    kinds = {item["kind"] for item in report["issues"]}
    assert "caption_overlap" in kinds
    assert "caption_escape" in kinds


def test_fast_mode_without_media_uses_zero_expectation(tmp_path: Path) -> None:
    video = tmp_path / "empty.mp4"
    video.write_bytes(b"mp4")
    report = qa_final.audit_final(
        video,
        output=tmp_path,
        state=ProjectState(),
        mode="fast",
        expected_frames=0,
        expected_samples=0,
    )
    assert report["expected_sec"] == 0.0
    assert report["status"] == "succeeded"


def test_word_fidelity_normalizes_names() -> None:
    from videoflow.application.qa_word_fidelity import normalize_wer_text

    assert normalize_wer_text("Huang e Nvidia") == normalize_wer_text(
        "Hwang e Invidia"
    )
    assert normalize_wer_text("Ação") == "acao"
    assert normalize_wer_text("clódi e emecêpê") == "claude e mcp"
