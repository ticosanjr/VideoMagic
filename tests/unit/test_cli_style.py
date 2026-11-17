"""`videoflow style` CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

from videoflow import cli


def test_style_cli_list_save_sync_and_learn(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    workspace = tmp_path / "workspace"

    assert cli.main(["style", "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert any(item["style_id"] == "canal-rafael-tech" for item in listed["styles"])

    source = tmp_path / "meu-estilo.md"
    source.write_text(
        "---\n"
        "style_id: meu-estilo\n"
        "name: Meu Estilo\n"
        "target_lufs: -14\n"
        "export_targets: [mp4_youtube, resolve]\n"
        "---\n\n"
        "# Direção\n\nCorpo inicial.\n",
        encoding="utf-8",
    )
    assert (
        cli.main(
            [
                "style",
                "save",
                str(source),
                "--workspace",
                str(workspace),
            ]
        )
        == 0
    )
    saved = json.loads(capsys.readouterr().out)
    assert saved["style_id"] == "meu-estilo"
    assert (workspace / "presets" / "meu-estilo.md").is_file()

    assert cli.main(["style", "learn", "meu-estilo", "--note", "Cortar antes de 1s"]) == 0
    learned = json.loads(capsys.readouterr().out)
    assert learned["count"] == 1

    assert (
        cli.main(
            [
                "style",
                "sync",
                "--workspace",
                str(workspace),
                "--overwrite",
            ]
        )
        == 0
    )
    synced = json.loads(capsys.readouterr().out)
    assert synced["ok"] is True


def test_style_cli_saves_a_slug_body(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))

    assert (
        cli.main(
            [
                "style",
                "save",
                "slug-novo",
                "--name",
                "Slug Novo",
                "--body",
                "# Corpo\n",
            ]
        )
        == 0
    )
    saved = json.loads(capsys.readouterr().out)
    assert saved["style_id"] == "slug-novo"
    assert Path(saved["file"]).is_file()


def test_style_cli_reports_style_errors(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    assert cli.main(["style", "save", "Bad ID", "--name", "Bad"]) == 1
    assert "style_error" in capsys.readouterr().err
