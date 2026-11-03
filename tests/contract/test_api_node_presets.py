from __future__ import annotations

from tests.contract.test_api_timeline import _client


def test_node_presets_create_edit_favorite_and_delete(monkeypatch, tmp_path) -> None:
    client, _manager = _client(monkeypatch, tmp_path)
    builtins = client.get(
        "/api/v1/node-presets", params={"step_type": "audio.vad"}
    ).json()["presets"]
    assert any(item["name"] == "Aggressive" and item["builtin"] for item in builtins)

    created = client.post(
        "/api/v1/node-presets",
        json={
            "step_type": "audio.vad",
            "name": "My podcast",
            "params": {"min_silence_ms": 500, "pad_before_ms": 100},
        },
    )
    assert created.status_code == 201, created.text
    preset = created.json()["preset"]

    updated = client.patch(
        f"/api/v1/node-presets/{preset['id']}",
        json={"name": "My podcast v2", "params": {"min_silence_ms": 620}},
    )
    assert updated.status_code == 200
    assert updated.json()["preset"]["name"] == "My podcast v2"

    favorite = client.post(
        f"/api/v1/node-presets/{preset['id']}/favorite",
        json={"favorite": True},
    )
    assert favorite.status_code == 200
    assert favorite.json()["preset"]["favorite"] is True

    listed = client.get(
        "/api/v1/node-presets", params={"step_type": "audio.vad"}
    ).json()["presets"]
    assert listed[0]["id"] == preset["id"]

    removed = client.delete(f"/api/v1/node-presets/{preset['id']}")
    assert removed.status_code == 200
    assert all(
        item["id"] != preset["id"]
        for item in client.get("/api/v1/node-presets").json()["presets"]
    )


def test_node_preset_errors_and_options(monkeypatch, tmp_path) -> None:
    client, _manager = _client(monkeypatch, tmp_path)
    assert client.get("/api/v1/node-options").status_code == 200
    assert client.patch(
        "/api/v1/node-presets/missing", json={"name": "x"}
    ).status_code in {404, 409}
    assert client.delete("/api/v1/node-presets/missing").status_code in {404, 409}
    assert client.post(
        "/api/v1/node-presets/missing/favorite", json={"favorite": True}
    ).status_code in {404, 409}
    assert client.get(
        "/api/v1/node-presets", params={"step_type": "edit.timeline"}
    ).json()["presets"]


def test_node_options_expose_configured_providers(monkeypatch, tmp_path) -> None:
    client, _manager = _client(monkeypatch, tmp_path)
    client.put(
        "/api/v1/providers/tts-demo",
        json={
            "id": "tts-demo",
            "name": "TTS demo",
            "capability": "tts",
            "base_url": "http://127.0.0.1:9/v1",
            "model": "tts-1",
            "api_key_env": "VIDEOWFLOW_TTS_API_KEY",
            "enabled": True,
        },
    )
    payload = client.get("/api/v1/node-options").json()
    assert payload["providers"]["tts"][0]["id"] == "tts-demo"
    assert payload["providers"]["tts"][0]["configured"] is True
    assert payload["providers"]["tts"][0]["missing"] == []
    assert isinstance(payload["services"], list)
    assert isinstance(payload["models"], list)

    client.put(
        "/api/v1/providers/llm-demo",
        json={
            "id": "llm-demo",
            "name": "LLM demo",
            "capability": "llm",
            "base_url": "http://127.0.0.1:9/v1",
            "model": "",
            "api_key_env": "",
            "enabled": True,
        },
    )
    payload = client.get("/api/v1/node-options").json()
    llm = next(item for item in payload["providers"]["llm"] if item["id"] == "llm-demo")
    assert llm["configured"] is False
    assert llm["missing"] == ["model"]
