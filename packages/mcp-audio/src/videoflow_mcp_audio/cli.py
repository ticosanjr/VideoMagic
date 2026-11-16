"""Console entry point for the audio MCP server."""

from __future__ import annotations

from .server import build_server


def main() -> None:
    """Run the audio MCP server over stdio."""

    build_server().run()


if __name__ == "__main__":
    main()
