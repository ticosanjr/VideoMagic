from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REFACTORED = (
    "src/videoflow/core/media_contract",
    "src/videoflow/mcp",
    "src/videoflow/api/routes_outputs",
    "src/videoflow/domains/media",
    "src/videoflow/domains/audio",
    "src/videoflow/domains/asr",
    "src/videoflow/domains/vision",
    "src/videoflow/domains/toolkit",
    "packages/gpu-worker/src/gpu_worker",
    "packages/vf-shared/src/vf_shared",
)

PENDING_SPLIT: set[str] = set()


def _python_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.py"))


def test_refactored_modules_stay_under_400_lines() -> None:
    failures: list[str] = []
    for relative in REFACTORED:
        root = ROOT / relative
        for path in _python_files(root):
            if "__pycache__" in path.parts:
                continue
            lines = len(path.read_text(encoding="utf-8").splitlines())
            relative = path.relative_to(ROOT).as_posix()
            if lines > 400 and relative not in PENDING_SPLIT:
                failures.append(f"{relative}: {lines} lines")
    assert not failures, "\n".join(failures)
