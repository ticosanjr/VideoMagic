"""Local filesystem browser: allowlist, filters, naming, and breadcrumbs."""

from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application import filesystem
from videoflow.domain.errors import (
    DirectoryExistsError,
    FilesystemError,
    InvalidDirectoryNameError,
    PathJailError,
    PathNotDirectoryError,
    PathNotFoundError,
    PermissionDeniedError,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    media = tmp_path / "media"
    (media / "clips").mkdir(parents=True)
    (media / "Interview.MP4").write_bytes(b"video")
    (media / "notes.txt").write_text("text", encoding="utf-8")
    (media / "clips" / "b-roll.mov").write_bytes(b"video")
    (media / ".hidden.mp4").write_bytes(b"video")
    return media


def test_list_directory_puts_directories_first_and_hides_dotfiles(
    root: Path,
) -> None:
    payload = filesystem.list_directory(root, roots=[root])

    assert [entry["name"] for entry in payload["entries"]] == [
        "clips",
        "Interview.MP4",
        "notes.txt",
    ]
    assert payload["entries"][0]["kind"] == "directory"
    assert payload["mode"] == "file"
    assert payload["can_write"] is True
    assert payload["truncated"] is False


def test_hidden_entries_can_be_requested(root: Path) -> None:
    payload = filesystem.list_directory(root, show_hidden=True, roots=[root])

    assert ".hidden.mp4" in {entry["name"] for entry in payload["entries"]}


def test_extension_filter_is_case_insensitive_and_normalised(root: Path) -> None:
    payload = filesystem.list_directory(
        root, extensions=["MP4", ".mov"], roots=[root]
    )

    names = {entry["name"] for entry in payload["entries"]}
    assert names == {"Interview.MP4", "clips"}
    assert all(
        entry["extension"] in {None, ".mp4", ".mov"}
        for entry in payload["entries"]
    )


def test_query_filter_and_limit(root: Path) -> None:
    payload = filesystem.list_directory(root, query="interview", roots=[root])
    assert [entry["name"] for entry in payload["entries"]] == ["Interview.MP4"]

    limited = filesystem.list_directory(root, limit=1, roots=[root])
    assert len(limited["entries"]) == 1
    assert limited["truncated"] is True


def test_directory_mode_only_lists_folders(root: Path) -> None:
    payload = filesystem.list_directory(root, mode="directory", roots=[root])

    assert [entry["name"] for entry in payload["entries"]] == ["clips"]
    assert payload["entries"][0]["selectable"] is True


def test_listing_rejects_bad_mode_and_paths(root: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported filesystem mode"):
        filesystem.list_directory(root, mode="socket", roots=[root])

    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(PathJailError):
        filesystem.list_directory(outside, roots=[root])

    with pytest.raises(PathNotFoundError):
        filesystem.list_directory(root / "missing", roots=[root])

    with pytest.raises(PathNotDirectoryError):
        filesystem.list_directory(root / "notes.txt", roots=[root])


def test_listing_without_a_usable_root_is_actionable(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    with pytest.raises(PathNotFoundError, match="No allowed directory"):
        filesystem.list_directory(None, roots=[missing])


def test_breadcrumbs_parent_and_root_labels(root: Path, tmp_path: Path) -> None:
    nested = root / "clips"
    payload = filesystem.list_directory(nested, roots=[tmp_path])

    assert payload["name"] == "clips"
    assert payload["parent"] is not None
    assert payload["parent"]["path"] == str(root)
    crumbs = [crumb["name"] for crumb in payload["breadcrumbs"]]
    assert crumbs[0] == tmp_path.name
    assert crumbs[-2:] == ["media", "clips"]

    top = filesystem.list_directory(tmp_path, roots=[tmp_path])
    assert top["parent"] is None
    assert len(top["breadcrumbs"]) == 1


def test_roots_payload_deduplicates_and_reports_state(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    payload = filesystem.roots_payload([tmp_path, tmp_path, missing])

    assert len(payload) == 2
    assert payload[0]["exists"] is True
    assert payload[0]["writable"] is True
    assert payload[1]["exists"] is False


def test_create_directory_returns_a_directory_entry(root: Path) -> None:
    payload = filesystem.create_directory(root, "  New folder  ", roots=[root])

    assert payload["name"] == "New folder"
    assert payload["kind"] == "directory"
    assert payload["selectable"] is True
    assert (root / "New folder").is_dir()

    with pytest.raises(DirectoryExistsError):
        filesystem.create_directory(root, "New folder", roots=[root])

    payload_path = filesystem.create_directory(str(root), "By path", roots=[root])
    assert Path(str(payload_path["path"])).is_dir()


@pytest.mark.parametrize(
    "name",
    [
        "",
        " ",
        ".",
        "..",
        "a/b",
        "a\\b",
        "bad\x01",
        "trailing.",
        "a:b",
        "CON",
        "lpt9.txt",
    ],
)
def test_invalid_directory_names_are_rejected(name: str) -> None:
    with pytest.raises(InvalidDirectoryNameError):
        filesystem.validate_directory_name(name)


def test_create_directory_maps_permission_failures(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "mkdir", fail)

    with pytest.raises(PermissionDeniedError):
        filesystem.create_directory(root, "blocked", roots=[root])


def test_create_directory_maps_os_errors(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "mkdir", fail)

    with pytest.raises(FilesystemError):
        filesystem.create_directory(root, "blocked", roots=[root])


def test_listing_maps_permission_and_os_errors(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(_path: Path) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(filesystem.os, "scandir", denied)
    with pytest.raises(PermissionDeniedError):
        filesystem.list_directory(root, roots=[root])

    def broken(_path: Path) -> None:
        raise OSError("unreadable")

    monkeypatch.setattr(filesystem.os, "scandir", broken)
    with pytest.raises(FilesystemError):
        filesystem.list_directory(root, roots=[root])


def test_entries_that_escape_the_allowlist_are_skipped(root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"video")
    (root / "escape.mp4").symlink_to(outside)

    payload = filesystem.list_directory(root, roots=[root])

    assert "escape.mp4" not in {entry["name"] for entry in payload["entries"]}


def test_modified_at_falls_back_to_epoch() -> None:
    assert filesystem._modified_at(0).startswith("1970-01-01")
    assert filesystem._modified_at(float("nan")).startswith("1970-01-01")


def test_writable_handles_os_errors(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert filesystem._writable(root) is True

    def fail(*_args: object, **_kwargs: object) -> bool:
        raise OSError("denied")

    monkeypatch.setattr(filesystem.os, "access", fail)
    assert filesystem._writable(root) is False
    assert filesystem._writable(root / "missing") is False


def test_root_label_uses_friendly_names(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(root))
    monkeypatch.setattr(filesystem.Path, "home", lambda: tmp_path)

    assert filesystem._root_label(tmp_path) == "Home"
    assert filesystem._root_label(root) == "VideoFlow data"
    assert filesystem._root_label(root / "clips") == "clips"


def test_scandir_entries_with_broken_stats_are_skipped(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = filesystem._entry_payload

    def flaky(path: Path, roots: object, mode: str, suffixes: object) -> object:
        if path.name == "notes.txt":
            raise OSError("bad stat")
        return original(path, roots, mode, suffixes)  # type: ignore[arg-type]

    monkeypatch.setattr(filesystem, "_entry_payload", flaky)

    payload = filesystem.list_directory(root, roots=[root])

    assert "notes.txt" not in {entry["name"] for entry in payload["entries"]}


def test_file_without_extension_reports_none(root: Path) -> None:
    (root / "README").write_text("text", encoding="utf-8")

    payload = filesystem.list_directory(root, roots=[root])
    entry = next(item for item in payload["entries"] if item["name"] == "README")

    assert entry["extension"] is None
