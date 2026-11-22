from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.scene_intel.pipeline import analyze_scene_project

pytestmark = pytest.mark.media


def ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if binary is None:
        pytest.skip("FFmpeg is not on PATH")
    return binary


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    target = tmp_path / "source.mp4"
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
            "color=c=red:s=320x180:r=30:d=3",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:r=30:d=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=6",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map",
            "[v]",
            "-map",
            "2:a",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-t",
            "6",
            str(target),
        ],
        check=True,
        capture_output=True,
    )
    return target


def test_scene_analysis_writes_manifest_and_keyframes(
    source: Path, tmp_path: Path
) -> None:
    media = FFmpegAdapter().probe(source)
    result = analyze_scene_project(
        source,
        tmp_path / "scenes",
        media=media,
        threshold=2.0,
        min_scene_len_sec=1.0,
    )
    assert result.cache_hit is False
    assert len(result.manifest.scenes) >= 2
    assert result.workspace.manifest.is_file()
    assert result.workspace.supercontext.is_file()
    payload = json.loads(result.workspace.manifest.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    for scene in result.manifest.scenes:
        assert scene.keyframe_path
        keyframe = Path(scene.keyframe_path)
        assert keyframe.is_file()
        assert keyframe.stat().st_size > 0
        assert keyframe.suffix == ".jpg"

    cached = analyze_scene_project(
        source,
        tmp_path / "scenes",
        media=media,
        threshold=2.0,
        min_scene_len_sec=1.0,
    )
    assert cached.cache_hit is True
    assert cached.engine == result.engine


def test_keyframe_respects_max_long_edge(source: Path, tmp_path: Path) -> None:
    media = FFmpegAdapter().probe(source)
    result = analyze_scene_project(
        source,
        tmp_path / "scenes",
        media=media,
        threshold=2.0,
        min_scene_len_sec=1.0,
        keyframe_size=256,
        force=True,
    )
    import cv2

    for scene in result.manifest.scenes:
        image = cv2.imread(str(scene.keyframe_path))
        assert image is not None
        assert max(image.shape[:2]) <= 256


def test_worker_scene_handler_returns_manifest_and_keyframe_zip(
    source: Path, tmp_path: Path
) -> None:
    import sys
    import zipfile

    package_src = (
        Path(__file__).resolve().parents[2] / "packages" / "gpu-worker" / "src"
    )
    if str(package_src) not in sys.path:
        sys.path.insert(0, str(package_src))
    from gpu_worker.gpu_handlers import make_scene_analyze_handler
    from gpu_worker.settings import Settings

    handler = make_scene_analyze_handler(Settings(work_dir=tmp_path / "worker"))
    outputs = handler(
        {
            "width": 320,
            "height": 180,
            "fps": 30,
            "sample_rate": 48_000,
            "duration_sec": 6.0,
            "threshold": 2.0,
            "min_scene_len_sec": 1.0,
            "source_topology": "single_16x9",
            "video_id": "sha-worker",
            "keyframe_size": 256,
        },
        [source],
        tmp_path / "job",
    )
    assert [path.name for path in outputs] == [
        "scenes_manifest.json",
        "scene_keyframes.zip",
    ]
    payload = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert payload["video_id"] == "sha-worker"
    assert len(payload["scenes"]) >= 2
    with zipfile.ZipFile(outputs[1]) as bundle:
        names = bundle.namelist()
    assert names
    assert all(name.startswith("keyframes/") for name in names)
