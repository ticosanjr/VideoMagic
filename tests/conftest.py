import pytest


@pytest.fixture(autouse=True)
def isolated_videoflow_home(monkeypatch, tmp_path):
    """Keep tests out of the developer's real VideoFlow data directory."""

    home = tmp_path / "videoflow-home"
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(home))
    yield
