"""The frozen-bundle source overlay used by fast releases."""

from __future__ import annotations

import sys
from pathlib import Path

import videoflow
from videoflow import _install_overlay, _OverlayFinder


def test_overlay_finder_resolves_modules_and_packages(tmp_path: Path) -> None:
    app = tmp_path / "app" / "videoflow"
    app.mkdir(parents=True)
    (app / "__init__.py").write_text("VALUE = 0\n", encoding="utf-8")
    (app / "thing.py").write_text("VALUE = 1\n", encoding="utf-8")
    package = app / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("VALUE = 2\n", encoding="utf-8")

    finder = _OverlayFinder(tmp_path / "app")
    module = finder.find_spec("videoflow.thing")
    assert module is not None
    assert module.origin == str(app / "thing.py")

    found = finder.find_spec("videoflow.pkg")
    assert found is not None
    assert found.submodule_search_locations == [str(package)]

    assert finder.find_spec("other.module") is None
    assert finder.find_spec("videoflow.missing") is None


def test_install_overlay_reads_the_bundle_version(
    tmp_path: Path, monkeypatch
) -> None:
    binary = tmp_path / "bundle" / "videoflow"
    binary.parent.mkdir()
    binary.write_text("", encoding="utf-8")
    app = binary.parent / "app"
    package = app / "videoflow"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (app / "version.txt").write_text("9.9.9\n", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(binary))
    monkeypatch.setattr(sys, "meta_path", list(sys.meta_path))
    monkeypatch.setattr(videoflow, "__version__", videoflow.__version__)

    _install_overlay()

    assert videoflow.__version__ == "9.9.9"
    assert isinstance(sys.meta_path[0], _OverlayFinder)

    monkeypatch.setattr(sys, "frozen", False, raising=False)
    _install_overlay()
    assert isinstance(sys.meta_path[0], _OverlayFinder)


def test_install_overlay_ignores_a_missing_bundle(
    tmp_path: Path, monkeypatch
) -> None:
    binary = tmp_path / "bundle" / "videoflow"
    binary.parent.mkdir()
    binary.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(binary))
    before = list(sys.meta_path)

    _install_overlay()

    assert sys.meta_path == before
