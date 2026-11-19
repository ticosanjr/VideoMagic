from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from videoflow.application.disk import (
    estimate_export_gb,
    prune_render_segments,
)


def test_export_estimate_uses_duration_and_sources(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x" * 1024)
    media = SimpleNamespace(
        duration_frames=1800,
        fps_num=30,
        fps_den=1,
        source_path=str(source),
    )
    state = SimpleNamespace(
        media_info=media,
        sources={"primary": media},
    )
    assert estimate_export_gb(state) >= 2.0


def test_prune_removes_alpha_and_segment_caches(tmp_path: Path) -> None:
    for relative in ("render/segments", "work/segments", "exports/.alpha", "work/.alpha"):
        target = tmp_path / relative
        target.mkdir(parents=True)
        (target / "cache.bin").write_bytes(b"x")
    removed = prune_render_segments(tmp_path)
    assert len(removed) >= 4
    assert not (tmp_path / "exports" / ".alpha").exists()
