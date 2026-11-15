"""Loopback static preview server for generated web scenes."""

from __future__ import annotations

import http.server
import secrets
import threading
from pathlib import Path
from urllib.parse import unquote, urlparse


class _SceneHandler(http.server.SimpleHTTPRequestHandler):
    token = ""
    root = Path(".")

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        prefix = f"/{self.token}/"
        if not parsed.path.startswith(prefix):
            return str(self.root / "__missing__")
        relative = unquote(parsed.path[len(prefix) :])
        target = (self.root / relative).resolve()
        if self.root.resolve() not in target.parents and target != self.root.resolve():
            return str(self.root / "__missing__")
        return str(target)

    def log_message(self, *_args: object) -> None:
        return None


class PreviewServer:
    def __init__(self) -> None:
        self._server: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.url = ""

    def start(self, root: Path) -> str:
        target = Path(root).expanduser().resolve()
        if not target.is_dir():
            raise FileNotFoundError(f"preview root does not exist: {target}")
        token = secrets.token_urlsafe(12)
        handler = type(
            "SceneHandler",
            (_SceneHandler,),
            {"token": token, "root": target},
        )
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(
            target=server.serve_forever,
            name="videoflow-web-preview",
            daemon=True,
        )
        thread.start()
        self._server = server
        self._thread = thread
        self.url = f"http://127.0.0.1:{server.server_address[1]}/{token}/"
        return self.url

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        self._server = None


preview_server = PreviewServer()
