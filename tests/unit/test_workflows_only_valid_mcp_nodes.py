"""v4.7.0 seed workflows, styles, and AGENTS contract."""

from __future__ import annotations

import json
from pathlib import Path

from videoflow.application.style_catalog import StyleCatalog, seed_styles_dir
from videoflow.application.workflow_catalog import WorkflowCatalog, seed_workflows_dir
from videoflow.domain.errors import VideoFlowError
from videoflow.steps.registry import get_step

OFFICIAL_STYLES = {
    "canal-paula-long",
    "canal-paula-reels",
    "canal-rafael-tech",
    "lf-cinema-doc-25d",
    "sr-viral-depth-split",
    "sr-feed-4x5-card",
}
DEAD_NODES = {
    "session.cull",
    "assets.plan",
    "timeline.apply_beatmap",
}


def test_every_seed_workflow_step_exists_in_the_registry(tmp_path: Path) -> None:
    catalog = WorkflowCatalog(root=tmp_path / "workflows", include_seeds=True)
    missing: list[str] = []
    for workflow in catalog.list_workflows():
        for step in workflow.steps:
            try:
                get_step(step.node)
            except VideoFlowError:
                missing.append(f"{workflow.workflow_id}:{step.node}")
    assert not missing, "\n".join(missing)


def test_seed_workflows_do_not_reference_removed_nodes() -> None:
    for path in sorted(seed_workflows_dir().glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for node in DEAD_NODES:
            assert node not in text, f"{path.name} still references {node}"


def test_seed_styles_are_the_six_official_styles(tmp_path: Path) -> None:
    catalog = StyleCatalog(root=tmp_path / "styles", include_seeds=True)
    styles = catalog.list_styles()
    assert {style.style_id for style in styles} == OFFICIAL_STYLES
    assert len(list(seed_styles_dir().glob("*.md"))) == 6
    for style in styles:
        punch = float(style.beatmap_defaults.get("punch_in_scale") or 1.0)
        assert punch <= 1.08, (style.style_id, punch)
        assert style.target_lufs == -16.0
        assert style.cut_rhythm.get("pacing_profile") in {"tight", "balanced"}


def test_workflow_default_and_compatible_styles_exist(tmp_path: Path) -> None:
    styles = {
        style.style_id
        for style in StyleCatalog(root=tmp_path / "styles", include_seeds=True).list_styles()
    }
    workflows = WorkflowCatalog(
        root=tmp_path / "workflows", include_seeds=True
    ).list_workflows()
    for workflow in workflows:
        if workflow.default_style:
            assert workflow.default_style in styles, workflow.workflow_id
        for style_id in workflow.compatible_styles:
            assert style_id in styles, (workflow.workflow_id, style_id)


def test_agents_template_is_short_and_teaches_the_v47_flow() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "videoflow"
        / "templates"
        / "opencode"
        / "AGENTS.md"
    )
    text = path.read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 85
    for marker in (
        'vf_decupage(action="review_packet")',
        'vf_transcript(action="editorial_map")',
        "image_to_broll_motion",
        "1.00 → 1.06",
        'qa_mode="skip"',
        "TALKING_HEAD",
    ):
        assert marker in text, marker
    for dead in DEAD_NODES:
        assert dead not in text, dead


def test_seed_styles_and_workflows_match_the_shipped_bundle() -> None:
    root = Path(__file__).resolve().parents[2]
    bundle = json.loads(
        (root / "videoflow-styles-workflows-otimizado.json").read_text(encoding="utf-8")
    )
    for kind, folder in (
        ("styles", root / "src" / "videoflow" / "styles"),
        ("workflows", root / "src" / "videoflow" / "workflows"),
    ):
        for entry in bundle[kind]:
            path = folder / f"{entry['id']}.md"
            assert path.is_file(), path
            assert path.read_text(encoding="utf-8") == entry["markdown_content"], path
