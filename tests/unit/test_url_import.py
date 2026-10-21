from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.application.url_import import import_url
from videoflow.domain.errors import CapabilityUnavailableError, IngestError


def test_url_import_invokes_ytdlp_and_returns_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    seen: list[list[str]] = []

    def fake_binary(name: str) -> str | None:
        return f"/usr/bin/{name}"

    def fake_run(command: list[str], **kwargs):
        seen.append(command)
        template = Path(command[command.index("-o") + 1])
        template.with_name(template.name.replace("%(ext)s", "mp4")).write_bytes(b"video")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("videoflow.application.url_import.find_binary", fake_binary)
    monkeypatch.setattr("videoflow.application.url_import.subprocess.run", fake_run)
    path = import_url(
        "https://example.com/video",
        max_height=720,
        allow_external_services=True,
    )
    assert path.is_file()
    assert "--no-playlist" in seen[0]
    assert "bv*[height<=720]+ba/b[height<=720]/b" in seen[0]


def test_url_import_rejects_non_http_schemes() -> None:
    with pytest.raises(IngestError):
        import_url("file:///tmp/video.mp4", allow_external_services=True)


def test_url_import_requires_ytdlp(monkeypatch) -> None:
    monkeypatch.setattr("videoflow.application.url_import.find_binary", lambda _name: None)
    with pytest.raises(CapabilityUnavailableError):
        import_url("https://example.com/video", allow_external_services=True)
