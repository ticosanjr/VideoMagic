from pathlib import Path

from videoflow.application.brand_templates import (
    BrandTemplate,
    apply_brand_options,
    delete_template,
    get_template,
    list_templates,
    save_template,
)
from videoflow.domain.config import CaptionStyle, OverlayConfig


def test_brand_template_roundtrip_and_apply(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    template = BrandTemplate(
        name="Studio",
        description="Bold captions",
        caption_style=CaptionStyle(primary_color="#FF0000"),
        overlay=OverlayConfig(enabled=True, asset="logo.png", position="top_left"),
    )
    save_template(template)
    assert get_template("Studio").caption_style.primary_color == "#FF0000"
    assert len(list_templates()) == 1
    options = apply_brand_options({}, "Studio")
    assert options["caption_primary_color"] == "#FF0000"
    assert options["overlay_asset"] == "logo.png"
    delete_template("Studio")
    assert list_templates() == []
