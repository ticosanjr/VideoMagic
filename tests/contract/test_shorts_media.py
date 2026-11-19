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


def test_short_render_with_varying_crop_keyframes(
    fixture: tuple[Path, Path], tmp_path: Path
) -> None:
    from videoflow.adapters.ffmpeg import FFmpegAdapter

    source, _ = fixture
    output = tmp_path / "crop.mp4"
    FFmpegAdapter().render_short(
        source,
        [(0, 2 * 48000)],
        output,
        sample_rate=48000,
        width=320,
        height=568,
        crop_focus_x=0.2,
        crop_focus_y=0.5,
        crop_keyframes=[(0.0, 0.2), (2.0, 0.8)],
    )
    assert output.is_file()
    assert output.stat().st_size > 0


def test_short_render_accepts_an_image_intro(
    fixture: tuple[Path, Path], tmp_path: Path
) -> None:
    import subprocess

    from videoflow.adapters.ffmpeg import FFmpegAdapter

    source, _ = fixture
    intro = tmp_path / "intro.png"
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
            "color=c=green:size=320x568",
            "-frames:v",
            "1",
            str(intro),
        ],
        check=True,
    )
    output = tmp_path / "intro-image.mp4"
    FFmpegAdapter().render_short(
        source,
        [(0, 2 * 48000)],
        output,
        sample_rate=48000,
        width=320,
        height=568,
        intro_path=intro,
        intro_duration_sec=1.0,
    )
    assert output.is_file()
    assert output.stat().st_size > 0


def test_short_render_accepts_alpha_webm_overlay(
    fixture: tuple[Path, Path], tmp_path: Path
) -> None:
    import subprocess

    from videoflow.adapters.ffmpeg import FFmpegAdapter

    source, _ = fixture
    overlay = tmp_path / "alpha.webm"
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
            "color=c=red@0.0:size=64x64:d=1",
            "-c:v",
            "libvpx-vp9",
            "-pix_fmt",
            "yuva420p",
            str(overlay),
        ],
        check=True,
    )
    output = tmp_path / "alpha-overlay.mp4"
    FFmpegAdapter().render_short(
        source,
        [(0, 2 * 48000)],
        output,
        sample_rate=48000,
        width=320,
        height=568,
        overlay_path=overlay,
        overlay_width_ratio=0.3,
    )
    assert output.is_file()
    assert output.stat().st_size > 0


def test_short_render_headline_and_picture_in_picture(
    fixture: tuple[Path, Path], tmp_path: Path
) -> None:
    import subprocess

    from videoflow.adapters.ffmpeg import FFmpegAdapter

    source, _ = fixture
    visual = tmp_path / "visual.png"
    overlay = tmp_path / "overlay.png"
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
            "color=c=blue:size=640x360",
            "-frames:v",
            "1",
            str(visual),
        ],
        check=True,
    )
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
            "color=c=red:size=160x160",
            "-frames:v",
            "1",
            str(overlay),
        ],
        check=True,
    )
    headline = tmp_path / "headline.mp4"
    FFmpegAdapter().render_short(
        source,
        [(0, 2 * 48000)],
        headline,
        sample_rate=48000,
        width=320,
        height=568,
        layout_mode="headline_card",
        cutout=True,
        headline_text="Titulo do Short",
    )
    pip = tmp_path / "pip.mp4"
    FFmpegAdapter().render_short(
        source,
        [(0, 2 * 48000)],
        pip,
        sample_rate=48000,
        width=320,
        height=568,
        layout_mode="pip_bottom_right",
        overlay_path=overlay,
        overlay_width_ratio=0.28,
    )
    split = tmp_path / "split.mp4"
    FFmpegAdapter().render_short(
        source,
        [(0, 2 * 48000)],
        split,
        sample_rate=48000,
        width=320,
        height=568,
        layout_mode="split_top_visual",
        visual_path=visual,
    )
    punch = tmp_path / "punch.mp4"
    FFmpegAdapter().render_short(
        source,
        [(0, 2 * 48000)],
        punch,
        sample_rate=48000,
        width=320,
        height=568,
        layout_mode="fullscreen_punchin",
        punch_in_scale=1.08,
    )
    assert headline.is_file() and headline.stat().st_size > 0
    assert pip.is_file() and pip.stat().st_size > 0
    assert split.is_file() and split.stat().st_size > 0
    assert punch.is_file() and punch.stat().st_size > 0


def test_short_render_mixes_music_and_sfx(
    fixture: tuple[Path, Path], tmp_path: Path
) -> None:
    import wave
    from array import array

    from videoflow.adapters.ffmpeg import FFmpegAdapter

    def write_tone(path: Path, *, frequency: int, seconds: float) -> Path:
        sample_rate = 48000
        samples = array("h")
        total = int(sample_rate * seconds)
        for index in range(total):
            value = int(8000 * ((index * frequency * 2) % sample_rate) / sample_rate - 4000)
            samples.append(value)
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate)
            handle.writeframes(samples.tobytes())
        return path

    source, _ = fixture
    music = write_tone(tmp_path / "music.wav", frequency=220, seconds=2)
    sfx = write_tone(tmp_path / "whoosh.wav", frequency=880, seconds=1)
    output = tmp_path / "mixed.mp4"

    FFmpegAdapter().render_short(
        source,
        [(0, 2 * 48000)],
        output,
        sample_rate=48000,
        music_path=music,
        music_volume=0.2,
        music_ducking=True,
        sfx_clips=[(sfx, 0.5, 0.8)],
    )

    assert output.is_file()
    probe = subprocess.run(
        [
            shutil.which("ffprobe") or "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type,channels",
            "-of",
            "json",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert stream["codec_type"] == "audio"


def test_mp4_render_burns_a_timeline_overlay(
    fixture: tuple[Path, Path], tmp_path: Path
) -> None:
    from videoflow.domain.state import (
        AudioSegment,
        MediaInfo,
        OverlayClip,
        ProjectState,
        VideoSegment,
    )
    from videoflow.exporters.mp4 import export_mp4

    source, _ = fixture
    logo = tmp_path / "logo.png"
    subprocess.run(
        [
            ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1",
            str(logo),
        ],
        check=True,
    )
    state = ProjectState(
        media_info=MediaInfo(
            source_path=str(source),
            duration_frames=60,
            fps_num=30,
            fps_den=1,
            width=640,
            height=360,
            audio_sample_rate=48000,
        ),
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_in_frame=0,
                source_out_frame=60,
                timeline_in_frame=0,
                timeline_out_frame=60,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_in_sample=0,
                source_out_sample=96000,
                timeline_in_sample=0,
                timeline_out_sample=96000,
            )
        ],
        overlays=[
            OverlayClip(
                overlay_id="o1",
                path=str(logo),
                start_frame=15,
                duration_frames=30,
                width_ratio=0.25,
            )
        ],
    )
    output = tmp_path / "overlay.mp4"

    export_mp4(state, output)

    assert output.is_file()
    assert output.stat().st_size > 1000
