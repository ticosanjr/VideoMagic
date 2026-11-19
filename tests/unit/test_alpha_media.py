from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from videoflow.application import alpha_media


def test_alpha_input_args_only_force_vp9_for_webm() -> None:
    assert alpha_media.alpha_input_args(Path("overlay.webm")) == ["-c:v", "libvpx-vp9"]
    assert alpha_media.alpha_input_args(Path("overlay.mov")) == []
    assert alpha_media.alpha_input_args(Path("overlay.mp4")) == []


def test_is_alpha_video_accepts_webm_and_mov() -> None:
    assert alpha_media.is_alpha_video(Path("a.WEBM")) is True
    assert alpha_media.is_alpha_video(Path("a.mov")) is True
    assert alpha_media.is_alpha_video(Path("a.mp4")) is False


def test_prepare_prores_overlay_returns_original_for_non_webm(tmp_path: Path) -> None:
    source = tmp_path / "overlay.mov"
    source.write_bytes(b"mov")
    assert alpha_media.prepare_prores_overlay(source) == source


def test_prepare_prores_overlay_converts_and_caches(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "overlay.webm"
    source.write_bytes(b"webm")
    cache = tmp_path / "cache"
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"prores")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(alpha_media, "find_binary", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(alpha_media.subprocess, "run", fake_run)

    first = alpha_media.prepare_prores_overlay(source, cache_dir=cache)
    second = alpha_media.prepare_prores_overlay(source, cache_dir=cache)

    assert first.is_file()
    assert first.suffix == ".mov"
    assert second == first
    assert len(calls) == 1
    assert "4444" in calls[0]
    assert "yuva444p10le" in calls[0]


def test_prepare_prores_overlay_falls_back_on_ffmpeg_error(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "overlay.webm"
    source.write_bytes(b"webm")
    monkeypatch.setattr(alpha_media, "find_binary", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        alpha_media.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="bad", stdout=""),
    )
    assert alpha_media.prepare_prores_overlay(source, cache_dir=tmp_path / "cache") == source
