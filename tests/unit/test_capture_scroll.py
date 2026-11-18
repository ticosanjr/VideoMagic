import base64
import json
from types import SimpleNamespace

from videoflow_mcp_vision import tools


def test_cdp_scroll_capture_drives_chromium(monkeypatch) -> None:
    sent: list[dict] = []

    class FakeSocket:
        def send(self, payload: str) -> None:
            sent.append(json.loads(payload))

        def recv(self) -> str:
            message = sent[-1]
            method = message.get("method")
            if method == "Runtime.evaluate":
                expression = str((message.get("params") or {}).get("expression", ""))
                value = "complete" if "readyState" in expression else True
                return json.dumps({"id": message["id"], "result": {"result": {"value": value}}})
            if method == "Page.captureScreenshot":
                return json.dumps(
                    {
                        "id": message["id"],
                        "result": {"data": base64.b64encode(b"PNG").decode("ascii")},
                    }
                )
            return json.dumps({"id": message["id"], "result": {}})

        def close(self) -> None:
            return None

    class FakeProcess:
        def terminate(self) -> None:
            return None

        def wait(self, timeout: int = 0) -> int:
            return 0

        def kill(self) -> None:
            return None

    class FakeResponse:
        status = 200

        def __init__(self, payload: dict | None = None) -> None:
            self.payload = payload or {}

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(tools, "_chrome", lambda: "/usr/bin/google-chrome")
    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: FakeProcess())

    def fake_urlopen(url, timeout=0):
        if url.endswith("/json/list"):
            return FakeResponse([{"type": "page", "webSocketDebuggerUrl": "ws://127.0.0.1:1/page"}])
        return FakeResponse({})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    fake_ws = SimpleNamespace(create_connection=lambda *args, **kwargs: FakeSocket())
    monkeypatch.setitem(__import__("sys").modules, "websocket", fake_ws)

    with tools._cdp_scroll_capture(
        "https://example.com",
        width=640,
        height=360,
        selector="#target",
        scroll_animation="bottom",
    ) as capture:
        assert capture(0.5) == b"PNG"

    assert any(item.get("method") == "Page.navigate" for item in sent)
    assert any("scrollIntoView" in str(item.get("params")) for item in sent)
