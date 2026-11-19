from __future__ import annotations

from types import SimpleNamespace

from videoflow.application import fonts
from videoflow.application.captions import CaptionLine, build_ass_lines
from videoflow.domain.config import CaptionStyle


def test_font_alias_resolves_without_fontconfig(monkeypatch) -> None:
    monkeypatch.setattr(fonts, "list_fonts", lambda: [])
    monkeypatch.setattr(fonts.shutil, "which", lambda name: None)
    assert fonts.resolve_font_family("Arial") == "Liberation Sans"
    assert fonts.font_available("Arial") is True
    assert fonts.resolve_font_family("Not A Font") is None


def test_resolve_font_family_prefers_registered_family(monkeypatch) -> None:
    monkeypatch.setattr(
        fonts,
        "list_fonts",
        lambda: [{"family": "Inter"}, {"family": ""}],
    )
    assert fonts.resolve_font_family("inter") == "Inter"
    assert fonts.resolve_font_family("") is None


def test_resolve_font_family_survives_a_broken_fontconfig(monkeypatch) -> None:
    monkeypatch.setattr(fonts, "list_fonts", lambda: [])
    monkeypatch.setattr(fonts.shutil, "which", lambda name: "/usr/bin/fc-match")

    def fail(command, **kwargs):
        raise OSError("fontconfig unavailable")

    monkeypatch.setattr(fonts.subprocess, "run", fail)
    assert fonts.resolve_font_family("Helvetica") == "Liberation Sans"


def test_fontconfig_match_resolves_metric_compatible_family(monkeypatch) -> None:
    monkeypatch.setattr(fonts, "list_fonts", lambda: [])
    monkeypatch.setattr(fonts.shutil, "which", lambda name: "/usr/bin/fc-match")

    def fake_run(command, **kwargs):
        requested = command[-1]
        family = "Liberation Sans" if requested == "Arial" else "DejaVu Sans"
        return SimpleNamespace(returncode=0, stdout=f"{family}\n", stderr="")

    monkeypatch.setattr(fonts.subprocess, "run", fake_run)
    assert fonts.resolve_font_family("Arial") == "Liberation Sans"
    assert fonts.resolve_font_family("Missing Font") is None


def test_caption_ass_uses_resolved_alias(monkeypatch) -> None:
    monkeypatch.setattr(fonts, "list_fonts", lambda: [])
    monkeypatch.setattr(fonts.shutil, "which", lambda name: None)
    ass = build_ass_lines(
        [CaptionLine(0, 1, "texto")],
        style=CaptionStyle(font_family="Arial"),
        width=1080,
        height=1920,
    )
    style_row = next(line for line in ass.splitlines() if line.startswith("Style:"))
    assert style_row.split(",")[1] == "Liberation Sans"
