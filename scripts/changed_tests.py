"""Pick the test files related to the current working-tree changes.

The fast gate uses this to avoid rerunning the entire suite for a small edit.
It is intentionally conservative: a changed backend module pulls in every test
whose filename mentions the module or its parent package, plus a tiny smoke
set. The full gate remains the authoritative check.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = (
    ROOT / "tests" / "unit" / "test_settings_and_voice_clone.py",
    ROOT / "tests" / "unit" / "test_cli.py",
)


def _git(*args: str) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def changed_paths() -> list[Path]:
    names = _git("diff", "--name-only", "HEAD")
    names += _git("ls-files", "--others", "--exclude-standard")
    return sorted({Path(name) for name in names})


def _matches(stem: str, folder: str) -> list[Path]:
    base = ROOT / "tests" / folder
    if not base.is_dir():
        return []
    candidates: list[Path] = []
    candidates.extend(base.glob(f"test_{stem}.py"))
    candidates.extend(base.glob(f"test_{stem}_*.py"))
    candidates.extend(base.glob(f"test_*{stem}*.py"))
    return candidates


def tests_for(path: Path) -> list[Path]:
    if path.suffix == ".py" and path.parts[:1] == ("tests",):
        target = ROOT / path
        return [target] if target.is_file() else []
    if path.suffix != ".py" or path.parts[:2] != ("src", "videoflow"):
        return []
    stem = path.stem
    candidates: list[Path] = []
    for folder in ("unit", "contract"):
        candidates.extend(_matches(stem, folder))
    parent = path.parent.name
    if parent and parent != "videoflow":
        for folder in ("unit", "contract"):
            base = ROOT / "tests" / folder
            if base.is_dir():
                candidates.extend(base.glob(f"test_{parent}_*.py"))
    return candidates


def main() -> int:
    paths = changed_paths()
    selected: set[Path] = set()
    python_changed = False
    for path in paths:
        if path.suffix == ".py":
            python_changed = True
        selected.update(tests_for(path))

    if python_changed:
        selected.update(SMOKE)

    for test in sorted(selected):
        if test.is_file():
            print(test.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
