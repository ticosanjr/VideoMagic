"""Canonical Markdown style catalog: parsing, sync, rules, and rulebook mapping."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.application.style_catalog import (
    StyleCatalog,
    parse_style_markdown,
    render_style_markdown,
    rulebook_from_style,
    style_slug,
)
from videoflow.domain.errors import StyleError, StyleNotFoundError
from videoflow.domain.headless import PresetRule, PresetRulebook
from videoflow.domain.styles import StyleDefinition


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))


def _style(style_id: str = "canal-teste", **updates) -> StyleDefinition:
    base = StyleDefinition(
        style_id=style_id,
        name="Canal Teste",
        aspect_ratio="9:16",
        target_lufs=-14.0,
        min_silence_ms=300,
        layout_mode="cutout",
        caption_preset="kinetic_highlight",
        motion_engine="hyperframes",
        palette=["#111827", "#f97316"],
        fonts=["Inter"],
        cut_rhythm={"median_cut_sec": 1.5},
        safe_zones={"reels": {"bottom": 0.18}},
        body="# Direção Visual\n\nCortes rápidos.",
        learned_rules=[PresetRule(id="r1", text="Cortar antes de 1s", scope="learned")],
    )
    return base.model_copy(update=updates)


def test_parse_render_roundtrip_keeps_rules_and_custom_fields() -> None:
    text = """---
schema_version: 1
style_id: canal-x
name: Canal X
aspect_ratio: "9:16"
target_lufs: -16.5
export_targets: [mp4_youtube, resolve]
palette: ["#000000"]
fonts: [Inter]
tags: [tech]
---

# Direção

Texto.

## Regras Aprendidas

- Regra um
- Regra um
"""

    style = parse_style_markdown(text)

    assert style.style_id == "canal-x"
    assert style.tags == ["tech"]
    assert [rule.text for rule in style.learned_rules] == ["Regra um"]
    rendered = render_style_markdown(style)
    again = parse_style_markdown(rendered)
    assert again.style_id == style.style_id
    assert again.learned_rules[0].text == "Regra um"
    assert again.model_extra == {"tags": ["tech"]}


def test_parse_rejects_invalid_frontmatter_and_slug() -> None:
    with pytest.raises(StyleError):
        parse_style_markdown("not markdown")
    with pytest.raises(StyleError):
        parse_style_markdown("---\nstyle_id: Bad ID\nname: X\n---\n")
    assert style_slug("Canal Paula — Reels/Shorts") == "canal-paula-reels-shorts"


def test_save_list_get_and_delete(tmp_path: Path) -> None:
    catalog = StyleCatalog(tmp_path / "styles", include_seeds=False)
    with pytest.raises(StyleNotFoundError):
        catalog.get("missing")
    path = catalog.save(_style())
    assert path.is_file()
    assert catalog.get("canal-teste").target_lufs == -14.0
    assert [item.style_id for item in catalog.list_styles()] == ["canal-teste"]
    payload = catalog.list_payload()[0]
    assert payload["summary"] == "Cortes rápidos."
    assert payload["file_path"] == str(path)
    with pytest.raises(StyleError):
        catalog.save(_style(), overwrite=False)
    assert catalog.delete("canal-teste") is True
    assert catalog.delete("canal-teste") is False


def test_learn_rule_merges_dedupes_caps_and_replaces(tmp_path: Path) -> None:
    catalog = StyleCatalog(tmp_path / "styles", include_seeds=False)
    catalog.save(_style())

    catalog.learn_rule("canal-teste", ["Cortar antes de 1s", "Nova regra"])
    style = catalog.get("canal-teste")
    assert len(style.learned_rules) == 2
    assert style.learned_rules[0].weight > 1.0

    catalog.learn_rule("canal-teste", ["Nova regra similar"], mode="merge")
    style = catalog.get("canal-teste")
    assert any(rule.text == "Nova regra similar" for rule in style.learned_rules)

    catalog.learn_rule(
        "canal-teste",
        [f"Regra {index}" for index in range(30)],
        mode="replace",
        max_rules=15,
    )
    style = catalog.get("canal-teste")
    assert len(style.learned_rules) == 15


def test_catalog_rejects_learning_for_missing_style(tmp_path: Path) -> None:
    catalog = StyleCatalog(tmp_path / "styles", include_seeds=False)
    with pytest.raises(StyleNotFoundError):
        catalog.learn_rule("novo-canal", ["Regra nova"])


def test_sync_copies_styles_and_preserves_local_edits(tmp_path: Path) -> None:
    catalog = StyleCatalog(tmp_path / "styles", include_seeds=False)
    catalog.save(_style())
    workspace = tmp_path / "workspace"

    first = catalog.sync(workspace)
    target = workspace / "presets" / "canal-teste.md"
    assert first["copied"] == ["canal-teste"]
    assert target.is_file()

    target.write_text(target.read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8")
    second = catalog.sync(workspace)
    assert second["skipped"] == ["canal-teste"]
    assert "local edit" in target.read_text(encoding="utf-8")

    third = catalog.sync(workspace, overwrite=True)
    assert third["copied"] == ["canal-teste"]
    assert "local edit" not in target.read_text(encoding="utf-8")
    manifest = json.loads(
        (workspace / "presets" / ".videoflow-styles.json").read_text(encoding="utf-8")
    )
    assert "canal-teste" in manifest


def test_rulebook_mapping_applies_style_defaults() -> None:
    book = rulebook_from_style(_style())

    assert isinstance(book, PresetRulebook)
    assert book.channel_id == "canal-teste"
    assert book.hard_constraints.aspect_ratio == "9:16"
    assert book.hard_constraints.cut_rhythm_sec == 1.5
    assert book.channel_kit.palette == ["#111827", "#f97316"]
    assert book.channel_kit.defaults["audio.master"]["target_lufs"] == -14.0
    assert book.channel_kit.defaults["audio.vad"]["min_silence_ms"] == 300
    assert book.channel_kit.defaults["layout.cutout"]["style"] == "cutout"
    assert book.channel_kit.defaults["motion.render"]["engine"] == "hyperframes"
    assert book.channel_kit.defaults["style"]["preset"]["name"] == "Canal Teste"
    assert book.learned_rules[0].text == "Cortar antes de 1s"


def test_seed_catalog_is_available(tmp_path: Path) -> None:
    catalog = StyleCatalog(tmp_path / "empty", include_seeds=True)
    ids = {style.style_id for style in catalog.list_styles()}
    assert {"canal-rafael-tech", "canal-paula-long", "canal-paula-reels"} <= ids
    assert catalog.path_for("canal-paula-reels").is_file()


def test_database_index_records_styles(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    from videoflow.application.database import list_styles_db

    catalog = StyleCatalog()
    catalog.save(_style("indexed-style"))

    assert any(item["style_id"] == "indexed-style" for item in list_styles_db())


def test_parse_rejects_unclosed_and_non_mapping_frontmatter() -> None:
    with pytest.raises(StyleError):
        parse_style_markdown("---\nstyle_id: x\n")
    with pytest.raises(StyleError):
        parse_style_markdown("---\n- one\n- two\n---\n")


def test_parse_falls_back_to_filename_and_rejects_bad_values() -> None:
    style = parse_style_markdown("---\nname: Sem id\n---\n", fallback_id="arquivo")
    assert style.style_id == "arquivo"
    with pytest.raises(StyleError):
        parse_style_markdown("---\nstyle_id: ok\nname: X\ntarget_lufs: 0\n---\n")


def test_style_from_rulebook_restores_legacy_preset_fields(tmp_path: Path) -> None:
    from videoflow.application.style_catalog import style_from_rulebook
    from videoflow.domain.headless import ChannelKit, PresetHardConstraints, PresetRulebook

    book = PresetRulebook(
        channel_id="legacy",
        hard_constraints=PresetHardConstraints(
            palette="light",
            aspect_ratio="9:16",
            caption_preset="kinetic",
            cut_rhythm_sec=2.0,
        ),
        channel_kit=ChannelKit(
            defaults={
                "style": {
                    "palette": ["#fff"],
                    "typography": {"family": "Inter"},
                    "cut_rhythm": {"median_cut_sec": 3.0},
                    "safe_zones": {"reels": {"bottom": 0.2}},
                }
            }
        ),
    )
    style = style_from_rulebook(book)
    assert style.palette == ["#fff"]
    assert style.fonts == ["Inter"]
    assert style.safe_zones["reels"]["bottom"] == 0.2
    assert style.aspect_ratio == "9:16"
    assert style.caption_preset == "kinetic"
    assert style.cut_rhythm["median_cut_sec"] == 3.0


def test_sync_reports_unchanged_and_handles_bad_manifest(tmp_path: Path) -> None:
    catalog = StyleCatalog(tmp_path / "styles", include_seeds=False)
    catalog.save(_style())
    workspace = tmp_path / "workspace"
    catalog.sync(workspace)
    (workspace / "presets" / ".videoflow-styles.json").write_text("[]", encoding="utf-8")

    result = catalog.sync(workspace)

    assert result["unchanged"] == ["canal-teste"]
    assert result["copied"] == []


def test_learn_rule_ignores_empty_notes_and_to_style_preset(tmp_path: Path) -> None:
    from videoflow.application.style_catalog import to_style_preset

    catalog = StyleCatalog(tmp_path / "styles", include_seeds=False)
    style = _style("canal-empty")
    catalog.save(style)
    updated = catalog.learn_rule("canal-empty", ["", "  "])
    assert [rule.text for rule in updated.learned_rules] == [
        rule.text for rule in style.learned_rules
    ]
    preset = to_style_preset(updated)
    assert preset.name == "Canal Teste"
    assert preset.source == "style:canal-empty"


def test_style_service_save_from_markdown(tmp_path: Path) -> None:
    from videoflow.application import style_service

    catalog = StyleCatalog(tmp_path / "styles", include_seeds=False)
    result = style_service.save_style(
        markdown_content=(
            "---\nstyle_id: md-style\nname: Markdown Style\ntarget_lufs: -15\n---\n\n# Corpo\n"
        ),
        updates={"body": "Corpo atualizado"},
        catalog=catalog,
    )
    assert result["style_id"] == "md-style"
    assert result["style"]["body"] == "Corpo atualizado"
    assert result["markdown"].startswith("---")


def test_invalid_yaml_and_invalid_files_are_rejected_or_skipped(tmp_path: Path) -> None:
    with pytest.raises(StyleError):
        parse_style_markdown("---\nstyle_id: [\n---\n")
    root = tmp_path / "styles"
    root.mkdir()
    (root / "broken.md").write_text("not markdown", encoding="utf-8")
    catalog = StyleCatalog(root, include_seeds=False)
    assert catalog.list_styles() == []
    bad = StyleDefinition.model_construct(style_id="Bad ID", name="Bad")
    with pytest.raises(StyleError):
        catalog.save(bad)


def test_learn_rule_consolidates_similar_rules(tmp_path: Path) -> None:
    catalog = StyleCatalog(tmp_path / "styles", include_seeds=False)
    catalog.save(_style("canal-similar", learned_rules=[]))
    catalog.learn_rule("canal-similar", ["Cortar antes de 1s"])
    catalog.learn_rule("canal-similar", ["Cortar antes de 1s sempre"])
    style = catalog.get("canal-similar")
    assert len(style.learned_rules) == 1
    assert style.learned_rules[0].text == "Cortar antes de 1s sempre"


def test_style_v2_fields_roundtrip_and_validation() -> None:
    import pytest

    from videoflow.application.style_catalog import (
        parse_style_markdown,
        render_style_markdown,
    )
    from videoflow.domain.styles import StyleDefinition

    style = StyleDefinition(
        style_id="v2-test",
        name="V2 Test",
        layout_mode="multicam_auto",
        motion_engine="ffmpeg+hyperframes",
        platforms=["youtube", "x"],
        beatmap_defaults={"linked_sfx": True},
        sound_design={"music_arc": "three_act"},
        hook_strategy="hook",
        intro_strategy="intro",
    )
    rendered = render_style_markdown(style)
    assert "platforms:" in rendered
    assert "beatmap_defaults:" in rendered
    parsed = parse_style_markdown(rendered)
    assert parsed.platforms == ["youtube", "x"]
    assert parsed.beatmap_defaults["linked_sfx"] is True

    with pytest.raises(ValueError, match="layout_mode"):
        StyleDefinition(style_id="bad-layout", name="Bad", layout_mode="unknown")
    with pytest.raises(ValueError, match="motion_engine"):
        StyleDefinition(style_id="bad-motion", name="Bad", motion_engine="unknown")


def test_style_duplicate_and_restore_seed(tmp_path: Path) -> None:
    from videoflow.application import style_service
    from videoflow.application.style_catalog import StyleCatalog

    catalog = StyleCatalog(tmp_path / "styles")
    style_service.save_style(
        style_id="custom-style",
        name="Custom",
        catalog=catalog,
    )
    duplicated = style_service.duplicate_style(
        "custom-style", new_id="custom-copy", catalog=catalog
    )
    assert duplicated["ok"] is True
    assert (tmp_path / "styles" / "custom-copy.md").is_file()

    restored = style_service.restore_style("canal-rafael-tech", catalog=catalog)
    assert restored["ok"] is True
    assert (tmp_path / "styles" / "canal-rafael-tech.md").is_file()


def test_twenty_two_styles_come_from_the_seed_directory(tmp_path) -> None:
    from videoflow.application.style_catalog import StyleCatalog, seed_styles_dir

    catalog = StyleCatalog(root=tmp_path / "user-styles")
    styles = catalog.list_styles()
    assert len(styles) == 22
    assert len(list(seed_styles_dir().glob("*.md"))) == 22


def test_packaging_bundles_the_seed_styles() -> None:
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[2]
    spec = (root / "packaging" / "videoflow.spec").read_text(encoding="utf-8")
    assert '"styles"), "videoflow/styles"' in spec


def test_vf_style_list_exposes_all_seed_styles() -> None:
    import asyncio

    from videoflow.mcp_server.server import build_server

    async def call() -> dict:
        server = build_server(profile="full")
        result = await server.call_tool("vf_style", {"action": "list"})
        return result.structured_content  # type: ignore[attr-defined]

    payload = asyncio.run(call())
    assert payload["ok"] is True
    assert len(payload["styles"]) == 22
