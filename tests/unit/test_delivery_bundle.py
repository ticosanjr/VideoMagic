"""Delivery bundle: alias expansion, artifacts, validation, and license gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.application.delivery_bundle import (
    DeliveryBundleRequest,
    build_delivery_bundle,
    timeline_frames,
)
from videoflow.application.export_service import resolve_targets
from videoflow.domain.errors import ExportError
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment


def _state(tmp_path: Path) -> ProjectState:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=90,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=48000,
    )
    return ProjectState(
        media_info=media,
        video_segments=[
            VideoSegment(
                clip_id="c1",
                source_in_frame=0,
                source_out_frame=60,
                timeline_in_frame=0,
                timeline_out_frame=60,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="c1",
                source_in_sample=0,
                source_out_sample=96000,
                timeline_in_sample=0,
                timeline_out_sample=96000,
            )
        ],
    )


class FakeAdapter:
    calls: list[list[str]] = []

    def render(self, command, progress=None):
        self.calls.append(list(command))
        Path(command[-1]).write_bytes(b"fake-mp4")


def test_resolve_targets_expands_all_and_youtube() -> None:
    assert resolve_targets("all") == ["mp4", "resolve", "premiere", "kdenlive"]
    assert resolve_targets(["mp4_youtube"]) == ["mp4"]
    assert resolve_targets(["youtube", "resolve"]) == ["mp4", "resolve"]
    assert resolve_targets(None) == ["resolve", "premiere", "kdenlive"]


def test_bundle_writes_every_target_and_manifest(tmp_path: Path) -> None:
    state = _state(tmp_path)

    result = build_delivery_bundle(
        state,
        tmp_path,
        request=DeliveryBundleRequest(),
        adapter=FakeAdapter(),
    )

    assert result["ok"] is True
    assert result["timeline_frames"] == 60
    assert set(result["files"]) == {"mp4", "resolve", "premiere", "kdenlive", "kdenlive_mlt"}
    for entry in result["files"].values():
        assert Path(entry["path"]).is_file()
        assert len(entry["sha256"]) == 64
    assert Path(result["files"]["resolve"]["path"]).name == "resolve_timeline.fcpxml"
    assert Path(result["files"]["premiere"]["path"]).name == "premiere_timeline.xml"
    assert Path(result["files"]["kdenlive"]["path"]).name == "kdenlive_project.kdenlive"
    assert Path(result["files"]["kdenlive_mlt"]["path"]).name == "kdenlive_project.mlt"
    assert Path(result["manifest"]).is_file()
    payload = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["validation"]["ok"] is True
    assert payload["mp4"]["profile"] == "youtube_h264"
    assert payload["mp4"]["loudness_lufs"] == -16.5


def test_bundle_rejects_blocked_license(tmp_path: Path) -> None:
    state = _state(tmp_path)
    clip = tmp_path / "assets" / "broll" / "clip.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"clip")
    (tmp_path / "broll.json").write_text(
        json.dumps({"clips": [{"path": "assets/broll/clip.mp4"}]}),
        encoding="utf-8",
    )
    licenses = tmp_path / "assets" / "licenses.json"
    licenses.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "title": "B-roll",
                        "path": "assets/broll/clip.mp4",
                        "license": "unknown",
                        "license_status": "unknown",
                        "page_url": "",
                    },
                    {
                        "title": "Unused stock",
                        "path": "assets/broll/unused.mp4",
                        "license": "unknown",
                        "license_status": "unknown",
                        "page_url": "",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ExportError, match="licenses need review"):
        build_delivery_bundle(state, tmp_path, adapter=FakeAdapter())


def test_bundle_ignores_unused_license_blockers(tmp_path: Path) -> None:
    state = _state(tmp_path)
    licenses = tmp_path / "assets" / "licenses.json"
    licenses.parent.mkdir(parents=True)
    licenses.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "asset_id": "unused",
                        "title": "Unused stock",
                        "path": "assets/broll/unused.mp4",
                        "license": "unknown",
                        "license_status": "unknown",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = build_delivery_bundle(state, tmp_path, adapter=FakeAdapter())
    assert result["ok"] is True


def test_bundle_skips_mp4_when_only_nle_targets(tmp_path: Path) -> None:
    state = _state(tmp_path)

    result = build_delivery_bundle(
        state,
        tmp_path,
        request=DeliveryBundleRequest(targets=("resolve", "kdenlive")),
        adapter=FakeAdapter(),
    )

    assert set(result["files"]) == {"resolve", "kdenlive", "kdenlive_mlt"}
    assert "mp4" not in result["validation"]["exports"]


def test_timeline_frames_uses_audio_when_longer(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.audio_segments[0].timeline_out_sample = 120000

    assert timeline_frames(state) == 75


def test_bundle_progress_sidecars_and_extra_targets(tmp_path: Path) -> None:
    state = _state(tmp_path)
    (tmp_path / "titles.ass").write_text("Dialogue: 0,0:00:00.00,0:00:01.00,,,", encoding="utf-8")
    audio = tmp_path / "audio"
    audio.mkdir()
    (audio / "master.wav").write_bytes(b"wav")
    seen: list[tuple[str, int]] = []

    result = build_delivery_bundle(
        state,
        tmp_path,
        request=DeliveryBundleRequest(targets=(), extra_targets=("resolve",)),
        adapter=FakeAdapter(),
        progress=lambda target, value: seen.append((target, value)),
    )

    assert set(result["files"]) == {"resolve"}
    assert result["mp4"]["audio_master"].endswith("audio/master.wav")
    assert result["sidecars"]
    assert seen and seen[-1][1] == 100


def test_bundle_cancels_before_writing(tmp_path: Path) -> None:
    from videoflow.domain.errors import JobCancelledError

    state = _state(tmp_path)
    with pytest.raises(JobCancelledError):
        build_delivery_bundle(
            state,
            tmp_path,
            request=DeliveryBundleRequest(targets=("resolve",)),
            adapter=FakeAdapter(),
            should_cancel=lambda: True,
        )


def test_bundle_mp4_reuses_master(tmp_path: Path) -> None:
    state = _state(tmp_path)
    audio = tmp_path / "audio"
    audio.mkdir()
    (audio / "master.wav").write_bytes(b"wav")

    seen: list[tuple[str, int]] = []
    result = build_delivery_bundle(
        state,
        tmp_path,
        request=DeliveryBundleRequest(targets=("mp4_youtube",)),
        adapter=FakeAdapter(),
        progress=lambda target, value: seen.append((target, value)),
    )

    assert result["ok"] is True
    assert ("mp4", 0) in seen
    assert result["files"]["mp4"]["path"].endswith("youtube_master.mp4")
    assert result["validation"]["exports"]["mp4"]["exists"] is True


def test_blocked_paths_and_empty_timeline(tmp_path: Path) -> None:
    from videoflow.application.delivery_bundle import blocked_paths

    paths = blocked_paths(
        [{"path": "a.wav", "title": "b.wav", "local_path": "c.wav", "asset_path": "d.wav"}],
        tmp_path,
    )
    assert {"a.wav", "b.wav", "c.wav", "d.wav"} <= paths
    assert blocked_paths([], tmp_path) == set()
    assert timeline_frames(ProjectState()) == 0


def test_bundle_defaults_to_all_targets_when_empty(tmp_path: Path) -> None:
    state = _state(tmp_path)

    result = build_delivery_bundle(
        state,
        tmp_path,
        request=DeliveryBundleRequest(targets=(), extra_targets=()),
        adapter=FakeAdapter(),
    )

    assert set(result["files"]) == {"mp4", "resolve", "premiere", "kdenlive", "kdenlive_mlt"}


def test_mp4_metadata_missing_and_probe(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application.delivery_bundle import _mp4_metadata

    assert _mp4_metadata(tmp_path / "missing.mp4") == {"exists": False}
    target = tmp_path / "clip.mp4"
    target.write_bytes(b"mp4")

    class Probe:
        def probe(self, path):
            from videoflow.domain.state import MediaInfo

            return MediaInfo(
                source_path=str(path),
                duration_frames=60,
                fps_num=30,
                fps_den=1,
                width=640,
                height=360,
                audio_sample_rate=48000,
            )

    import videoflow.adapters.ffmpeg as ffmpeg_module

    monkeypatch.setattr(ffmpeg_module, "FFmpegAdapter", Probe)
    metadata = _mp4_metadata(target)
    assert metadata["duration_frames"] == 60


def test_bundle_burns_subtitles_by_default(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import delivery_bundle

    state = _state(tmp_path)
    (tmp_path / "subtitles.ass").write_text("[Events]\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_export(state, path, **kwargs):
        captured.update(kwargs)
        Path(path).write_bytes(b"fake-mp4")
        return Path(path)

    monkeypatch.setattr(delivery_bundle, "render_master", fake_export)
    result = build_delivery_bundle(
        state,
        tmp_path,
        request=DeliveryBundleRequest(targets=("mp4_youtube",)),
        adapter=FakeAdapter(),
    )

    assert result["ok"] is True
    assert Path(str(captured["ass_path"])) == tmp_path / "subtitles.ass"

    captured.clear()
    build_delivery_bundle(
        state,
        tmp_path,
        request=DeliveryBundleRequest(targets=("mp4_youtube",), burn_subtitles=False),
        adapter=FakeAdapter(),
    )
    assert captured["ass_path"] is None


def test_resolve_subtitle_track_prefers_merged_captions(tmp_path: Path) -> None:
    from videoflow.application.subtitles import resolve_subtitle_track

    assert resolve_subtitle_track(tmp_path) is None
    (tmp_path / "titles.ass").write_text("[Events]\n", encoding="utf-8")
    assert resolve_subtitle_track(tmp_path) == tmp_path / "titles.ass"
    (tmp_path / "subtitles.ass").write_text("[Events]\n", encoding="utf-8")
    assert resolve_subtitle_track(tmp_path) == tmp_path / "subtitles.ass"
