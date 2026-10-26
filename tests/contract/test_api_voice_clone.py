from __future__ import annotations

from pathlib import Path

from tests.contract.test_api_timeline import _client


def test_voice_clone_shell_consent_and_unavailable(monkeypatch, tmp_path: Path) -> None:
    client, _manager = _client(monkeypatch, tmp_path)
    status = client.get("/api/v1/voice-clone/status").json()
    assert status["available"] is False
    assert status["consent_required"] is True

    rejected = client.post(
        "/api/v1/voice-clone/profiles",
        json={"name": "Host", "consent_ref": "", "sample_count": 0},
    )
    assert rejected.status_code == 422

    created = client.post(
        "/api/v1/voice-clone/profiles",
        json={
            "name": "Host",
            "consent_ref": "signed-2026-10-26",
            "sample_count": 3,
            "metadata": {"language": "pt-BR"},
        },
    )
    assert created.status_code == 201, created.text
    profile = created.json()["profile"]
    assert profile["provider"] == "none"
    assert profile["consent_ref"] == "signed-2026-10-26"

    listed = client.get("/api/v1/voice-clone/profiles").json()["profiles"]
    assert [item["id"] for item in listed] == [profile["id"]]

    synth = client.post(
        "/api/v1/voice-clone/synthesize",
        json={"profile_id": profile["id"], "text": "hello"},
    )
    assert synth.status_code == 501
    assert synth.json()["detail"]["code"] == "not_implemented"

    removed = client.delete(f"/api/v1/voice-clone/profiles/{profile['id']}")
    assert removed.status_code == 200
    assert client.get("/api/v1/voice-clone/profiles").json()["profiles"] == []
