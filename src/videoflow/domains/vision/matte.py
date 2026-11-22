"""Background removal with MediaPipe selfie segmentation or rembg."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from ..toolkit import commands, storage
from ..toolkit.assets import (
    _ensure_input,
    _ffmpeg,
    _materialize_remote,
    _payload,
    _require_output,
)
from ..toolkit.errors import (
    MissingCommandError,
    OutputNotProducedError,
)
from . import common
from .common import (
    VIDEO_EXTENSIONS,
    _probe_stream,
    _validate_fps,
)


def remove_background(
    project_id: str,
    input_path: str,
    is_video: bool = False,
) -> dict[str, Any]:
    """Remove an image or video background with rembg."""

    tool = "remove_background"
    source = _ensure_input(input_path, "input_path")
    if not is_video and source.suffix.lower() in VIDEO_EXTENSIONS:
        is_video = True
    key = storage.cache_key(tool, storage.file_fingerprint(source), bool(is_video))
    if is_video:
        relative = f"assets/matte/{source.stem}_alpha.webm"
    else:
        relative = f"assets/matte/{source.stem}_alpha.png"

    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")

    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)

    if is_video:
        if common.ROUTER.health("segment_matte"):
            try:
                result = common.ROUTER.submit(
                    "segment_matte",
                    {
                        "input": str(source),
                        "fps": 30,
                        "model": os.environ.get("VF_MATTE_MODEL", "u2net"),
                        "output_name": f"{source.stem}_alpha.webm",
                    },
                )
                record = _materialize_remote(
                    project_id=project_id,
                    relative_path=relative,
                    result=result,
                    capability="segment_matte",
                    cache_key=key,
                    kind="broll",
                )
                _require_output(target)
                return _payload(tool, project_id, record, mode="remote", fallback=False)
            except Exception:  # noqa: BLE001 - local fallback is the contract
                pass
        _matte_video(source, target)
    else:
        _run_rembg(source, target)

    _require_output(target)
    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind=("broll" if is_video else "images"),
        license="source",
        source="local:rembg",
        cache_key=key,
        metadata={"is_video": bool(is_video), "input": str(source)},
    )
    return _payload(tool, project_id, record, mode="local")


def _matte_backend() -> str:
    requested = os.environ.get("VF_MATTE_BACKEND", "auto").strip().lower()
    if requested in {"mediapipe", "selfie"}:
        return "mediapipe"
    if requested in {"rembg", "u2net", "u2netp"}:
        return "rembg"
    # MediaPipe keeps one segmenter in memory; the rembg CLI reloads its
    # model per frame, which turns a 3 s clip into minutes.
    if importlib.util.find_spec("mediapipe") is not None:
        return "mediapipe"
    if importlib.util.find_spec("rembg") is not None or shutil.which("rembg"):
        return "rembg"
    return "rembg"


def _matte_frame(source: Path, target: Path) -> None:
    """Cut one frame with the cheapest backend available."""

    if _matte_backend() == "mediapipe" and _mediapipe_selfie(source, target):
        return
    _run_rembg(source, target)


def _selfie_model_path() -> Path | None:
    """Return a local MediaPipe selfie model, downloading it once if needed."""

    configured = Path(
        os.environ.get("VF_SELFIE_MODEL", "")
    ).expanduser() if os.environ.get("VF_SELFIE_MODEL") else None
    root = Path(
        os.environ.get("VIDEOFLOW_HOME")
        or (Path.home() / ".videoflow")
    ).expanduser()
    candidates = [
        configured,
        root / "models" / "selfie_segmenter.tflite",
        Path("models") / "selfie_segmenter.tflite",
        Path("models") / "selfie_segmenter_landscape.tflite",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    target = root / "models" / "selfie_segmenter.tflite"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        import urllib.request

        url = (
            "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
            "selfie_segmenter/float16/1/selfie_segmenter.tflite"
        )
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = response.read()
        if len(payload) < 1024:
            return None
        target.write_bytes(payload)
        return target
    except Exception:  # noqa: BLE001 - offline is a valid environment
        return None


_SELFIE_SEGMENTERS: dict[str, Any] = {}


def _selfie_segmenter(model: Path) -> Any:
    """Create one MediaPipe segmenter per process instead of per frame."""

    key = str(model)
    cached = _SELFIE_SEGMENTERS.get(key)
    if cached is not None:
        return cached
    import mediapipe as mp  # noqa: F401 - initialize the runtime once
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import (
        ImageSegmenter,
        ImageSegmenterOptions,
        RunningMode,
    )

    options = ImageSegmenterOptions(
        base_options=BaseOptions(model_asset_path=str(model)),
        running_mode=RunningMode.IMAGE,
        output_confidence_masks=True,
        output_category_mask=False,
    )
    segmenter = ImageSegmenter.create_from_options(options)
    _SELFIE_SEGMENTERS[key] = segmenter
    return segmenter


def _mediapipe_selfie(source: Path, target: Path) -> bool:
    """Run MediaPipe selfie segmentation and write an RGBA PNG."""

    try:
        import cv2
        import mediapipe as mp
        import numpy as np
    except Exception:  # noqa: BLE001 - backend is optional
        return False
    model = _selfie_model_path()
    if model is None:
        return False
    frame = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if frame is None:
        return False
    try:
        segmenter = _selfie_segmenter(model)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=np.ascontiguousarray(rgb),
        )
        result = segmenter.segment(image)
        masks = result.confidence_masks or ()
        if not masks:
            return False
        candidate = masks[1] if len(masks) > 1 else masks[0]
        mask = np.squeeze(candidate.numpy_view())
    except Exception:  # noqa: BLE001 - optional backend
        return False
    alpha = np.clip(mask * 255.0, 0, 255).astype("uint8")
    bgra = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = alpha
    return bool(cv2.imwrite(str(target), bgra))


def _run_rembg_directory(source_dir: Path, target_dir: Path) -> bool:
    """Run rembg once for the whole frame directory, reusing one model load."""

    if os.environ.get("VF_REMBG_CMD"):
        return False
    model = os.environ.get("VF_MATTE_MODEL", "u2netp").strip()
    model_args = ["-m", model] if model else []
    binary = shutil.which("rembg")
    if binary:
        command = [binary, "p", *model_args, str(source_dir), str(target_dir)]
    elif importlib.util.find_spec("rembg") is not None:
        command = [
            sys.executable,
            "-m",
            "rembg",
            "p",
            *model_args,
            str(source_dir),
            str(target_dir),
        ]
    else:
        return False
    try:
        commands.run(command)
    except Exception:  # noqa: BLE001 - fall back to one frame at a time
        return False
    return True


def _matte_video(source: Path, target: Path) -> None:
    ffmpeg = _ffmpeg()
    fps = os.environ.get("VF_MATTE_FPS", "30")
    _validate_fps(fps)
    maximum = int(os.environ.get("VF_MATTE_MAX_WIDTH", "720"))
    try:
        width = float(_probe_stream(source).get("width") or 0)
    except Exception:  # noqa: BLE001 - probe is advisory
        width = 0.0
    scale = ""
    if maximum > 0 and width > maximum:
        scale = f",scale='min({maximum},iw)':-2"
    with tempfile.TemporaryDirectory(prefix="vf-matte-") as raw:
        workdir = Path(raw)
        frames = workdir / "frames"
        mattes = workdir / "matte"
        frames.mkdir()
        mattes.mkdir()
        commands.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(source),
                "-vf",
                f"fps={fps}{scale}",
                str(frames / "%06d.png"),
            ]
        )
        extracted = sorted(frames.glob("*.png"))
        if not extracted:
            raise OutputNotProducedError(
                "FFmpeg extracted no frames for background removal",
                details={"input": str(source)},
            )
        batched = _matte_backend() == "rembg" and _run_rembg_directory(frames, mattes)
        if batched and all(
            (mattes / frame.name).is_file() for frame in extracted
        ):
            pass
        else:
            for index, frame in enumerate(extracted, start=1):
                _matte_frame(frame, mattes / f"{index:06d}.png")
        commands.run(
            [
                ffmpeg,
                "-y",
                "-framerate",
                fps,
                "-i",
                str(mattes / "%06d.png"),
                "-c:v",
                "libvpx-vp9",
                "-pix_fmt",
                "yuva420p",
                "-b:v",
                "0",
                "-crf",
                "30",
                str(target),
            ]
        )


def _run_rembg(source: Path, target: Path) -> None:
    model = os.environ.get("VF_MATTE_MODEL", "u2netp").strip()
    template = os.environ.get("VF_REMBG_CMD")
    if template:
        commands.run(
            commands.expand_template(
                template,
                {"input": str(source), "output": str(target), "model": model},
                name="rembg command",
            )
        )
        return
    model_args = ["-m", model] if model else []
    binary = shutil.which("rembg")
    if binary:
        commands.run([binary, "i", *model_args, str(source), str(target)])
        return
    if importlib.util.find_spec("rembg") is not None:
        commands.run(
            [sys.executable, "-m", "rembg", "i", *model_args, str(source), str(target)]
        )
        return
    raise MissingCommandError(
        "rembg is not installed; set VF_REMBG_CMD or install rembg",
        details={"env": ["VF_REMBG_CMD"], "capability": "matte"},
    )
