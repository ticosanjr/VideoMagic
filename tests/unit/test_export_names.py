from __future__ import annotations

from datetime import datetime
from pathlib import Path

from videoflow.application.export_names import (
    fixed_basename,
    safe_stem,
    timestamped_basename,
    unique_basename,
    unique_path,
)


def test_timestamped_basename_uses_source_and_local_stamp() -> None:
    name = timestamped_basename(
        Path("/tmp/Kimi.mp4"),
        now=datetime(2026, 11, 5, 14, 30, 12),
    )
    assert name == "Kimi_VideoFlow_Edited_261105143012"


def test_safe_stem_replaces_unsafe_characters() -> None:
    assert safe_stem(Path("A b:c.mp4")) == "A_b_c"
    assert safe_stem(Path("...mp4")) == "video"


def test_unique_path_appends_a_counter(tmp_path: Path) -> None:
    first = unique_path(tmp_path, "Kimi_VideoFlow_Edited_261105143012.mp4")
    assert first.name == "Kimi_VideoFlow_Edited_261105143012.mp4"
    first.write_bytes(b"one")
    second = unique_path(tmp_path, first.name)
    assert second.name == "Kimi_VideoFlow_Edited_261105143012_1.mp4"
    second.write_bytes(b"two")
    third = unique_path(tmp_path, first.name)
    assert third.name == "Kimi_VideoFlow_Edited_261105143012_2.mp4"


def test_unique_basename_checks_all_suffixes(tmp_path: Path) -> None:
    base = "Kimi_VideoFlow_Edited_261105143012"
    (tmp_path / f"{base}.xml").write_bytes(b"x")
    assert (
        unique_basename(tmp_path, base, (".fcpxml", ".xml"))
        == f"{base}_1"
    )


def test_fixed_basename_strips_known_suffixes() -> None:
    assert fixed_basename("my.timeline.fcpxml") == "my.timeline"
    assert fixed_basename("a/b") == "b"
    assert fixed_basename("...") == "timeline"
