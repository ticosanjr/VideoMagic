import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.packaging
def test_latest_appimage_smoke() -> None:
    candidates = sorted(
        (ROOT / "releases").glob("v*/VideoFlow-*-x86_64.AppImage"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        pytest.skip("no staged AppImage")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "smoke_appimage.py"),
            "--appimage",
            str(candidates[0]),
        ],
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
