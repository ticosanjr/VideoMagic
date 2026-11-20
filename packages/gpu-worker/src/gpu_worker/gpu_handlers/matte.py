"""Background matte handlers with a cached rembg session."""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gpu_worker.gpu_handlers.common import _ffmpeg, _run
from gpu_worker.handlers import Handler, HandlerError
from gpu_worker.progress import report

if TYPE_CHECKING:
    from gpu_worker.models import ModelRegistry
    from gpu_worker.settings import Settings

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_MATTE_SESSIONS: dict[str, Any] = {}
_MATTE_LOCK = threading.RLock()

def _matte_session(
    name: str,
    models: ModelRegistry | None = None,
) -> Any:
    """Return a cached rembg session instead of reloading the model per job."""

    key = str(name or "u2net")
    with _MATTE_LOCK:
        session = _MATTE_SESSIONS.get(key)
        if session is not None:
            if models is not None:
                models.touch(f"rembg:{key}")
            return session
        try:
            from rembg import new_session
        except Exception as exc:  # noqa: BLE001 - optional dependency
            raise HandlerError(f"rembg is not installed: {exc}") from exc
        session = new_session(key)
        _MATTE_SESSIONS[key] = session
        if models is not None:

            def unload() -> None:
                _MATTE_SESSIONS.pop(key, None)

            models.register(
                f"rembg:{key}",
                capability="segment_matte",
                unload=unload,
                metadata={"model": key},
            )
        return session


def make_segment_matte_handler(
    settings: Settings,
    models: ModelRegistry | None = None,
) -> Handler:
    """Remove the background from an image or a short video clip."""

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise HandlerError("segment_matte requires an input artifact")
        try:
            from rembg import remove
        except Exception as exc:  # noqa: BLE001 - optional dependency
            raise HandlerError(f"rembg is not installed: {exc}") from exc
        report("loading matte model", 10)
        session = _matte_session(str(params.get("model") or "u2net"), models)
        source = input_paths[0]
        if source.suffix.casefold() in IMAGE_SUFFIXES:
            target = work_dir / "matte.png"
            report("removing background", 40)
            target.write_bytes(remove(source.read_bytes(), session=session))
            return [target]
        ffmpeg = _ffmpeg(settings)
        fps = int(params.get("fps") or 30)
        with tempfile.TemporaryDirectory(prefix="vf-matte-", dir=work_dir) as raw:
            frames_dir = Path(raw) / "frames"
            matte_dir = Path(raw) / "matte"
            frames_dir.mkdir()
            matte_dir.mkdir()
            _run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-vf",
                    f"fps={fps}",
                    str(frames_dir / "%06d.png"),
                ]
            )
            frames = sorted(frames_dir.glob("*.png"))
            if not frames:
                raise HandlerError("segment_matte extracted no frames")
            total = len(frames)
            for index, frame in enumerate(frames, start=1):
                (matte_dir / f"{index:06d}.png").write_bytes(
                    remove(frame.read_bytes(), session=session)
                )
                if index == 1 or index % 10 == 0 or index == total:
                    report("removing background", 15 + round(75 * index / total))
            report("encoding matte", 95)
            target = work_dir / "matte.webm"
            _run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-framerate",
                    str(fps),
                    "-i",
                    str(matte_dir / "%06d.png"),
                    "-c:v",
                    "libvpx-vp9",
                    "-pix_fmt",
                    "yuva420p",
                    "-b:v",
                    "0",
                    "-crf",
                    "24",
                    str(target),
                ]
            )
        if not target.is_file():
            raise HandlerError("segment_matte did not create the output")
        return [target]

    return handler
