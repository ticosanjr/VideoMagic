from __future__ import annotations

from pathlib import Path

from videoflow.domains.vision import graphics_web as tools


def test_encode_frames_forces_even_dimensions(tmp_path: Path, monkeypatch) -> None:
    frames = tmp_path / "frames"
    frames.mkdir()
    target = tmp_path / "out.mp4"
    seen: list[list[str]] = []

    monkeypatch.setattr(tools, "_ffmpeg", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(tools.commands, "run", lambda argv, **kwargs: seen.append(list(argv)))
    tools._encode_frames(frames, target, fps=5, duration=0.2, alpha=False)
    assert seen
    argv = seen[0]
    assert "scale=trunc(iw/2)*2:trunc(ih/2)*2" in argv
    assert argv[-1] == str(target)
