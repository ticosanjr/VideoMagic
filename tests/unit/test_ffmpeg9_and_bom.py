"""FFmpeg 7/8/9 filter scripts, UTF-8 BOM settings, caption burn and AAC tolerance."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.unit.test_mp4_export_edges import FakeRenderer
from videoflow.adapters.ffmpeg import helpers as ffmpeg_helpers
from videoflow.adapters.ffmpeg.helpers import (
    FILTER_COMPLEX_SCRIPT_FLAG,
    FilterScriptUnsupportedError,
    build_filter_complex_args,
    probe_filter_script_flag,
)
from videoflow.core.media_contract.models import ExpectedMedia, MediaReport
from videoflow.core.media_contract.validate import _check_expected
from videoflow.domain.errors import ExportError
from videoflow.exporters import mp4
from videoflow.exporters.mp4 import SubtitleBurnError, export_mp4


def _sample_state(tmp_path: Path):
    from tests.contract.test_exporters import sample_state

    return sample_state(tmp_path)


def _fake_ffmpeg(tmp_path: Path, *, new: bool, old: bool) -> Path:
    name = "ffmpeg-new" if new and not old else "ffmpeg-old" if old and not new else "ffmpeg-both"
    path = tmp_path / name
    lines = ["#!/bin/sh", "for arg in \"$@\"; do"]
    if new:
        lines.extend(['  if [ "$arg" = "-/filter_complex" ]; then exit 0; fi'])
    if old:
        lines.extend([f'  if [ "$arg" = "{FILTER_COMPLEX_SCRIPT_FLAG}" ]; then exit 0; fi'])
    lines.extend(["done", "exit 1", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.mark.skipif(os.name == "nt", reason="shell fake FFmpeg is POSIX-only")
def test_probe_prefers_the_ffmpeg9_file_option(tmp_path: Path) -> None:
    probe_filter_script_flag.cache_clear()
    binary = _fake_ffmpeg(tmp_path, new=True, old=False)
    try:
        assert probe_filter_script_flag(str(binary)) == "-/filter_complex"
    finally:
        probe_filter_script_flag.cache_clear()


@pytest.mark.skipif(os.name == "nt", reason="shell fake FFmpeg is POSIX-only")
def test_probe_falls_back_to_the_ffmpeg6_script_flag(tmp_path: Path) -> None:
    probe_filter_script_flag.cache_clear()
    binary = _fake_ffmpeg(tmp_path, new=False, old=True)
    try:
        assert probe_filter_script_flag(str(binary)) == FILTER_COMPLEX_SCRIPT_FLAG
    finally:
        probe_filter_script_flag.cache_clear()


@pytest.mark.skipif(os.name == "nt", reason="shell fake FFmpeg is POSIX-only")
def test_probe_fails_closed_when_neither_flag_works(tmp_path: Path) -> None:
    probe_filter_script_flag.cache_clear()
    binary = _fake_ffmpeg(tmp_path, new=False, old=False)
    try:
        with pytest.raises(FilterScriptUnsupportedError) as captured:
            probe_filter_script_flag(str(binary))
        assert captured.value.code == "ffmpeg_unsupported_filter_script"
    finally:
        probe_filter_script_flag.cache_clear()


def test_small_graph_stays_inline(tmp_path: Path) -> None:
    graph = "null"
    assert build_filter_complex_args(
        graph, tmp_path / "graph.txt", ffmpeg_bin="ffmpeg"
    ) == ["-filter_complex", graph]


def test_large_graph_uses_the_new_flag_and_writes_utf8_without_bom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ffmpeg_helpers,
        "probe_filter_script_flag",
        lambda _binary: "-/filter_complex",
    )
    graph = "null;" * 2_000
    script = tmp_path / "graph.txt"
    args = build_filter_complex_args(
        graph, script, ffmpeg_bin="ffmpeg", inline_limit=10
    )
    assert args == ["-/filter_complex", str(script)]
    assert script.read_text(encoding="utf-8") == graph
    assert not script.read_bytes().startswith(b"\xef\xbb\xbf")


def test_large_graph_uses_the_old_flag_when_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ffmpeg_helpers,
        "probe_filter_script_flag",
        lambda _binary: FILTER_COMPLEX_SCRIPT_FLAG,
    )
    script = tmp_path / "graph.txt"
    args = build_filter_complex_args(
        "null;" * 2_000, script, ffmpeg_bin="ffmpeg", inline_limit=10
    )
    assert args == [FILTER_COMPLEX_SCRIPT_FLAG, str(script)]


def test_filter_script_args_uses_the_probed_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ffmpeg_helpers,
        "probe_filter_script_flag",
        lambda _binary: "-/filter_complex",
    )
    graph = "null;" * 2_000
    args, directory = ffmpeg_helpers._filter_script_args(
        ["ffmpeg", "-filter_complex", graph, "-map", "[out]"],
        ffmpeg_bin="ffmpeg",
    )
    assert directory is not None
    try:
        assert args[1] == "-/filter_complex"
        assert Path(args[2]).is_file()
        assert args[3:] == ["-map", "[out]"]
    finally:
        import shutil

        shutil.rmtree(directory, ignore_errors=True)


def test_settings_json_with_windows_bom_loads_and_saves_clean(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    from videoflow.application.settings import (
        AppSettings,
        load_settings,
        save_settings,
        settings_path,
    )

    payload = AppSettings().model_dump(mode="json")
    payload["paths"]["ffmpeg"] = "/custom/ffmpeg"
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\ufeff" + json.dumps(payload), encoding="utf-8")
    loaded = load_settings()
    assert loaded.paths.ffmpeg == "/custom/ffmpeg"
    save_settings(loaded)
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_missing_or_empty_ass_fails_closed(tmp_path: Path) -> None:
    state = _sample_state(tmp_path)
    renderer = FakeRenderer()
    missing = tmp_path / "missing.ass"
    with pytest.raises(SubtitleBurnError) as captured:
        export_mp4(
            state,
            tmp_path / "missing.mp4",
            adapter=renderer,
            ass_path=missing,
            burn_subtitles=True,
        )
    assert captured.value.code == "subtitle_burn_failed"
    empty = tmp_path / "empty.ass"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(SubtitleBurnError):
        export_mp4(
            state,
            tmp_path / "empty.mp4",
            adapter=renderer,
            ass_path=empty,
            burn_subtitles=True,
        )


def test_valid_ass_is_burned_and_can_be_explicitly_disabled(tmp_path: Path) -> None:
    state = _sample_state(tmp_path)
    ass = tmp_path / "captions.ass"
    ass.write_text("[Script Info]\n", encoding="utf-8")
    renderer = FakeRenderer()
    export_mp4(
        state,
        tmp_path / "burned.mp4",
        adapter=renderer,
        ass_path=ass,
        burn_subtitles=True,
    )
    graph = renderer.commands[0][renderer.commands[0].index("-filter_complex") + 1]
    assert "ass=" in graph

    disabled = FakeRenderer()
    export_mp4(
        state,
        tmp_path / "plain.mp4",
        adapter=disabled,
        ass_path=tmp_path / "missing.ass",
        burn_subtitles=False,
    )
    graph = disabled.commands[0][disabled.commands[0].index("-filter_complex") + 1]
    assert "ass=" not in graph


def test_master_export_forwards_burn_and_qa_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from videoflow.application import master_export

    state = _sample_state(tmp_path)
    captured: dict[str, object] = {}

    def fake_export(*_args, **kwargs):
        captured.update(kwargs)
        return tmp_path / "master.mp4"

    monkeypatch.setattr(master_export, "export_mp4", fake_export)
    ass = tmp_path / "captions.ass"
    ass.write_text("[Script Info]\n", encoding="utf-8")
    master_export.render_master(
        state,
        tmp_path / "master.mp4",
        output=tmp_path,
        ass_path=ass,
        burn_subtitles=True,
        qa_mode="off",
    )
    assert captured["burn_subtitles"] is True
    assert captured["qa_mode"] == "off"


def test_qa_mode_off_disables_the_delivery_gate(tmp_path: Path) -> None:
    missing = tmp_path / "missing.mp4"
    mp4._validate_delivery(missing, None, qa_mode="off")
    with pytest.raises(ExportError):
        mp4._validate_delivery(missing, None, qa_mode="fast")


def _media_report(duration: float, *, with_audio: bool) -> MediaReport:
    return MediaReport(
        ok=True,
        kind="deliverable",
        path="deliverable.mp4",
        metrics={
            "format": {"duration_sec": duration, "size": 1},
            "video": {"nb_frames": None, "fps_num": 60, "fps_den": 1},
            "audio": {"sample_rate": 48000, "channels": 2} if with_audio else None,
        },
    )


def test_aac_padding_within_45ms_is_tolerated_at_60fps() -> None:
    expected = ExpectedMedia(
        duration_sec=10.0,
        fps_num=60,
        fps_den=1,
        sample_rate=48000,
        channels=2,
    )
    report = _media_report(10.04, with_audio=True)
    _check_expected(report, expected)
    assert report.errors == []


def test_aac_drift_beyond_45ms_still_fails() -> None:
    expected = ExpectedMedia(
        duration_sec=10.0,
        fps_num=60,
        fps_den=1,
        sample_rate=48000,
        channels=2,
    )
    report = _media_report(10.051, with_audio=True)
    _check_expected(report, expected)
    assert any(item["code"] == "duration_mismatch" for item in report.errors)


def test_video_only_keeps_the_one_frame_tolerance() -> None:
    expected = ExpectedMedia(
        duration_sec=10.0,
        fps_num=60,
        fps_den=1,
        sample_rate=48000,
        channels=2,
    )
    report = _media_report(10.04, with_audio=False)
    _check_expected(report, expected)
    assert any(item["code"] == "duration_mismatch" for item in report.errors)


def test_ffmpeg_supports_filter_complex_script_reports_probe_failure(monkeypatch) -> None:
    from videoflow.adapters.ffmpeg import helpers

    def unsupported(_binary: str) -> str:
        raise helpers.FilterScriptUnsupportedError("unsupported")

    monkeypatch.setattr(helpers, "probe_filter_script_flag", unsupported)
    assert helpers.ffmpeg_supports_filter_complex_script("ffmpeg") is False
    monkeypatch.setattr(helpers, "probe_filter_script_flag", lambda _binary: "-/filter_complex")
    assert helpers.ffmpeg_supports_filter_complex_script("ffmpeg") is True
