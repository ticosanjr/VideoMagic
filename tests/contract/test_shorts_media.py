import json
import shutil
import subprocess
from pathlib import Path

import pytest

from videoflow import cli

pytestmark = pytest.mark.media


def ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if binary is None:
        pytest.skip("FFmpeg is not on PATH")
    return binary


@pytest.fixture()
def fixture(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=6",
            "-af",
            "volume=0:enable='between(t,1,2)+between(t,3,4)'",
            "-t",
            "6",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )
    transcript = tmp_path / "subs.srt"
    transcript.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nFirst line.\n\n"
        "2\n00:00:02,000 --> 00:00:03,000\nSecond line.\n\n"
        "3\n00:00:04,000 --> 00:00:06,000\nThird line.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VIDEOWFLOW_FFMPEG", ffmpeg())
    return source, transcript


def test_multi_piece_concat_renders(fixture: tuple[Path, Path], tmp_path: Path) -> None:
    from videoflow.adapters.ffmpeg import FFmpegAdapter

    source, _ = fixture
    output = tmp_path / "concat.mp4"
    FFmpegAdapter().render_short(
        source,
        [(0, 48000), (2 * 48000, 3 * 48000)],
        output,
        sample_rate=48000,
    )
    assert output.is_file()
    probe = subprocess.run(
        [
            shutil.which("ffprobe") or "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert (stream["width"], stream["height"]) == (1080, 1920)


def test_cli_renders_vertical_shorts(fixture: tuple[Path, Path], tmp_path: Path) -> None:
    source, transcript = fixture
    output = tmp_path / "out"
    assert (
        cli.main(
            [
                "shorts",
                str(source),
                "--transcript",
                str(transcript),
                "-o",
                str(output),
                "--count",
                "2",
                "--min-sec",
                "1",
                "--max-sec",
                "3",
            ]
        )
        == 0
    )
    report = json.loads((output / "shorts.json").read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert len(report["clips"]) == 2
    for clip in report["clips"]:
        path = Path(clip["path"])
        assert path.is_file()
        probe = subprocess.run(
            [
                shutil.which("ffprobe") or "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        stream = json.loads(probe.stdout)["streams"][0]
        assert stream["width"] == 1080
        assert stream["height"] == 1920
