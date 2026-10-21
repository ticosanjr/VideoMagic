from pathlib import Path

import pytest

from videoflow.application.project_templates import (
    ProjectTemplate,
    export_config,
    get_template,
    import_config,
    list_templates,
    save_template,
)
from videoflow.domain.errors import FilesystemError


def test_project_template_filters_paths_and_roundtrips(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    template = ProjectTemplate(
        name="Studio",
        description="Full run",
        options={
            "source": "/secret/source.mp4",
            "output": "/secret/out",
            "caption_font_size": 90,
            "music_enabled": True,
        },
    )
    saved = save_template(template)
    assert "source" not in saved["options"]
    assert "output" not in saved["options"]
    assert get_template("Studio").options["caption_font_size"] == 90
    assert len(list_templates()) == 1
    envelope = export_config({"transcript": "/secret.srt", "zooms": True})
    assert envelope["schema_version"] == 1
    assert "transcript" not in envelope["options"]
    assert import_config(envelope)["zooms"] is True


def test_config_import_rejects_unknown_schema() -> None:
    with pytest.raises(FilesystemError):
        import_config({"schema_version": 99, "options": {}})
