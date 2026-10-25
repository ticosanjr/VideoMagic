"""Edge branches shared by the exporters and the incremental cache."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.unit.test_incremental_render import FakeAdapter, state
from videoflow.domain.errors import ExportError
from videoflow.exporters import common
from videoflow.exporters.incremental import (
    NotEligible,
    _aligned,
    export_mp4_incremental,
)


def test_require_timeline_rejects_clips_past_the_media(tmp_path: Path) -> None:
    payload = state(tmp_path)
    payload.video_segments[0].source_out_frame = 999
    with pytest.raises(ExportError, match="exceeds the media duration"):
        common.require_timeline(payload)

    payload = state(tmp_path)
    payload.audio_segments[0].source_out_sample = 10**9
    with pytest.raises(ExportError, match="exceeds the media duration"):
        common.require_timeline(payload)

    payload = state(tmp_path)
    payload.audio_segments[0].timeline_in_sample = 4800
    with pytest.raises(ExportError, match="not packed"):
        common.require_timeline(payload)

    payload = state(tmp_path)
    payload.audio_segments[1].clip_id = "v1"
    with pytest.raises(ExportError, match="Duplicate audio clip id"):
        common.require_timeline(payload)


def test_require_timeline_returns_timebase_and_ids(tmp_path: Path) -> None:
    media, video, audio = common.require_timeline(state(tmp_path))
    assert set(video) == {"v1", "v2"}
    assert set(audio) == {"v1", "v2"}
    assert common.rate_parts(media).fps_num == 30


def test_write_text_removes_the_temporary_file_on_failure(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "out" / "file.txt"

    def fail(source, destination):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        common.write_text(target, "data")
    assert list((tmp_path / "out").glob("*.tmp")) == []


def test_incremental_rejects_unaligned_and_missing_inputs(tmp_path: Path) -> None:
    payload = state(tmp_path)
    payload.video_segments[0].transform.scale = 1.2
    with pytest.raises(NotEligible):
        export_mp4_incremental(payload, tmp_path / "out.mp4", adapter=FakeAdapter())

    payload = state(tmp_path)
    payload.video_segments[0].transform.type = "punch_in"
    with pytest.raises(NotEligible):
        export_mp4_incremental(payload, tmp_path / "out.mp4", adapter=FakeAdapter())

    payload = state(tmp_path)
    payload.audio_segments.pop()
    with pytest.raises(ExportError, match="mismatch"):
        export_mp4_incremental(payload, tmp_path / "out.mp4", adapter=FakeAdapter())

    payload = state(tmp_path)
    payload.audio_segments[0].source_out_sample += 4800
    with pytest.raises(NotEligible, match="audio not aligned"):
        export_mp4_incremental(payload, tmp_path / "out.mp4", adapter=FakeAdapter())

    payload = state(tmp_path)
    payload.media_info.source_path = str(tmp_path / "offline.mp4")
    with pytest.raises(ExportError, match="offline"):
        export_mp4_incremental(payload, tmp_path / "out.mp4", adapter=FakeAdapter())


def test_aligned_rejects_missing_and_shifted_audio(tmp_path: Path) -> None:
    payload = state(tmp_path)
    media = payload.media_info
    assert media is not None
    payload.audio_segments.pop()
    assert _aligned(payload, media, 30.0) is False
    payload = state(tmp_path)
    payload.audio_segments[0].source_in_sample = 4800
    assert _aligned(payload, payload.media_info, 30.0) is False


def test_incremental_crossfade_without_audio_overlap(tmp_path: Path) -> None:
    from videoflow.domain.state import Transition

    payload = state(tmp_path)
    payload.video_segments[0].transition_out = Transition(type="crossfade", audio=False)
    adapter = FakeAdapter()
    export_mp4_incremental(payload, tmp_path / "out.mp4", adapter=adapter)
    assert adapter.segments == 3
    assert adapter.concats == 1


def test_incremental_empty_render_and_progress(tmp_path: Path) -> None:
    class EmptyAdapter(FakeAdapter):
        def render(self, args, **kwargs):
            target = Path(args[-1])
            target.write_bytes(b"")
            return target

    with pytest.raises(ExportError, match="empty render"):
        export_mp4_incremental(state(tmp_path), tmp_path / "empty.mp4", adapter=EmptyAdapter())

    seen: list[int] = []
    export_mp4_incremental(
        state(tmp_path),
        tmp_path / "progress.mp4",
        adapter=FakeAdapter(),
        progress=seen.append,
    )
    assert seen[-1] == 100


def test_incremental_overlay_branches(tmp_path: Path) -> None:
    from videoflow.domain.state import OverlayClip

    missing = tmp_path / "missing.png"
    payload = state(tmp_path)
    payload.overlays = [
        OverlayClip(overlay_id="bad", path=str(missing), start_frame=0, duration_frames=10)
    ]
    with pytest.raises(ExportError, match="Overlay is offline"):
        export_mp4_incremental(payload, tmp_path / "out.mp4", adapter=FakeAdapter())

    video = tmp_path / "overlay.mp4"
    video.write_bytes(b"video")
    payload.overlays = [
        OverlayClip(
            overlay_id="clip",
            path=str(video),
            start_frame=0,
            duration_frames=10,
            kind="video",
        )
    ]
    adapter = FakeAdapter()
    export_mp4_incremental(payload, tmp_path / "out.mp4", adapter=adapter)
    assert adapter.segments == 1  # base segments were cached by the failed pass
    assert adapter.concats == 1
