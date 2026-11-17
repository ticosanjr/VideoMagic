"""Channel style cloning and rule learning through vf_project."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from videoflow.application import style_clone
from videoflow.application.preset_rules import load_rulebook


def _image(path: Path, color: tuple[int, int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), color).save(path)
    return path


def test_clone_style_from_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    references = tmp_path / "prints"
    _image(references / "one.png", (10, 20, 30))
    _image(references / "two.jpg", (200, 30, 20))

    result = style_clone.clone_style(
        "canal-paula",
        tmp_path / "out",
        reference_dir=str(references),
        name="Paula",
    )

    assert result["ok"] is True
    assert result["channel_id"] == "canal-paula"
    assert result["preset"]["palette"]
    book = load_rulebook("canal-paula")
    assert book.channel_kit.palette == result["preset"]["palette"]
    assert book.channel_kit.defaults["style"]["preset"]["name"] == "Paula"
    assert Path(result["rulebook"]).is_file()


def test_clone_style_url_without_browser_warns(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(style_clone, "find_binary", lambda *args: None)

    result = style_clone.clone_style(
        "canal-rafael",
        tmp_path / "out",
        reference_url="https://example.test/reel",
    )

    assert result["ok"] is True
    assert result["warnings"]
    assert "chromium_not_found" in result["warnings"][0]


def test_learn_rule_merge_and_replace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))

    first = style_clone.learn_rule(
        "canal-paula",
        tmp_path / "out",
        notes=["legendas grandes", "cortes de 2 segundos"],
    )
    assert first["count"] == 2

    second = style_clone.learn_rule(
        "canal-paula",
        tmp_path / "out",
        notes=["legendas grandes"],
    )
    assert second["count"] == 2

    replaced = style_clone.learn_rule(
        "canal-paula",
        tmp_path / "out",
        notes=["nova regra"],
        mode="replace",
    )
    assert replaced["count"] == 1
    from videoflow.application.style_catalog import StyleCatalog

    style = StyleCatalog().get("canal-paula")
    assert style.learned_rules[0].text == "nova regra"


def test_clone_style_captures_url_and_records_font(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    browser = tmp_path / "chrome"
    browser.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "for arg in sys.argv:\n"
        "    if arg.startswith('--screenshot='):\n"
        "        target = pathlib.Path(arg.split('=', 1)[1])\n"
        "        target.parent.mkdir(parents=True, exist_ok=True)\n"
        "        target.write_bytes(b'PNG')\n",
        encoding="utf-8",
    )
    browser.chmod(0o755)
    monkeypatch.setattr(style_clone, "find_binary", lambda *args: str(browser))

    original = style_clone.StyleReverseStep.run

    def fake_run(self, context, params, io):
        original(self, context, params, io)
        preset = dict(context.metadata["style_preset"])
        preset["typography"] = {"family": "Inter"}
        context.metadata["style_preset"] = preset

    monkeypatch.setattr(style_clone.StyleReverseStep, "run", fake_run)

    result = style_clone.clone_style(
        "canal-url",
        tmp_path / "out",
        reference_url="https://example.test/reel",
    )

    assert result["warnings"] == []
    assert (tmp_path / "out" / "style" / "reference.png").is_file()
    assert load_rulebook("canal-url").channel_kit.fonts == ["Inter"]


def test_capture_reference_failure_is_reported(tmp_path: Path, monkeypatch) -> None:
    browser = tmp_path / "chrome-fail"
    browser.write_text("#!/bin/sh\necho boom >&2\nexit 3\n", encoding="utf-8")
    browser.chmod(0o755)
    monkeypatch.setattr(style_clone, "find_binary", lambda *args: str(browser))

    error = style_clone._capture_reference("https://example.test", tmp_path / "ref.png")

    assert "boom" in error


def test_cut_rhythm_and_video_reference_helpers(tmp_path: Path, monkeypatch) -> None:
    class Completed:
        returncode = 0
        stderr = "pts_time:0.0\npts_time:1.5\npts_time:4.0\npts_time:4.5\n"

    monkeypatch.setattr(style_clone, "find_binary", lambda *args: "/usr/bin/ffmpeg")
    monkeypatch.setattr(style_clone.subprocess, "run", lambda *a, **k: Completed())
    rhythm = style_clone._cut_rhythm(tmp_path / "ref.mp4")
    assert rhythm == {
        "mode": "measured",
        "min_cut_sec": 0.5,
        "max_cut_sec": 2.5,
        "median_cut_sec": 1.5,
    }

    monkeypatch.setattr(style_clone, "find_binary", lambda *args: None)
    assert style_clone._download_reference_video("https://x.test", tmp_path) is None
    assert style_clone._sample_video_frames(tmp_path / "ref.mp4", tmp_path) == []


def test_clone_style_samples_video_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    references = tmp_path / "prints"
    references.mkdir()
    (references / "clip.mp4").write_bytes(b"video")
    monkeypatch.setattr(style_clone, "_sample_video_frames", lambda *a, **k: [])
    monkeypatch.setattr(
        style_clone,
        "_cut_rhythm",
        lambda *a, **k: {
            "mode": "measured",
            "min_cut_sec": 1.0,
            "max_cut_sec": 2.0,
            "median_cut_sec": 1.5,
        },
    )

    result = style_clone.clone_style(
        "canal-video",
        tmp_path / "out",
        reference_dir=str(references),
    )

    assert result["preset"]["cut_rhythm"]["median_cut_sec"] == 1.5


def test_video_reference_download_and_frame_sampling(tmp_path: Path, monkeypatch) -> None:
    class Completed:
        returncode = 0
        stderr = ""

    def fake_run(argv, **kwargs):
        target = Path(argv[argv.index("-o") + 1]) if "-o" in argv else None
        if target is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"video")
        else:
            frames = Path(argv[-1]).parent
            frames.mkdir(parents=True, exist_ok=True)
            (frames / "frame-001.png").write_bytes(b"PNG")
        return Completed()

    monkeypatch.setattr(style_clone, "find_binary", lambda *args: "/usr/bin/tool")
    monkeypatch.setattr(style_clone.subprocess, "run", fake_run)

    downloaded = style_clone._download_reference_video("https://x.test/reel", tmp_path)
    assert downloaded is not None and downloaded.is_file()
    frames = style_clone._sample_video_frames(downloaded, tmp_path)
    assert frames and frames[0].endswith("frame-001.png")

    class Failed(Completed):
        returncode = 2

    monkeypatch.setattr(style_clone.subprocess, "run", lambda *a, **k: Failed())
    assert style_clone._download_reference_video("https://x.test", tmp_path) is None
    assert style_clone._sample_video_frames(downloaded, tmp_path) == []
    assert style_clone._cut_rhythm(downloaded) is None


def test_clone_style_url_with_video_samples_rhythm(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    video = tmp_path / "ref.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(style_clone, "_download_reference_video", lambda *a, **k: video)
    monkeypatch.setattr(style_clone, "_sample_video_frames", lambda *a, **k: [])
    monkeypatch.setattr(
        style_clone,
        "_cut_rhythm",
        lambda *a, **k: {
            "mode": "measured",
            "min_cut_sec": 0.5,
            "max_cut_sec": 1.5,
            "median_cut_sec": 1.0,
        },
    )

    result = style_clone.clone_style(
        "canal-reel",
        tmp_path / "out",
        reference_url="https://x.test/reel",
    )

    assert result["preset"]["cut_rhythm"]["median_cut_sec"] == 1.0


def test_clone_style_without_references_warns(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    result = style_clone.clone_style("canal-empty", tmp_path / "out")
    assert any("no reference" in warning for warning in result["warnings"])
