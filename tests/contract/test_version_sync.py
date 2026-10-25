from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_python_and_ui_versions_are_in_lockstep() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    python_version = re.search(r'^version = "([^"]+)"', pyproject, re.M)
    assert python_version is not None
    package = json.loads((ROOT / "ui" / "package.json").read_text(encoding="utf-8"))
    init = (ROOT / "src" / "videoflow" / "__init__.py").read_text(encoding="utf-8")
    init_version = re.search(r'__version__ = "([^"]+)"', init)
    assert init_version is not None
    assert package["version"] == python_version.group(1) == init_version.group(1)
    assert "__APP_VERSION__" in (ROOT / "ui" / "src" / "lib" / "version.ts").read_text()
