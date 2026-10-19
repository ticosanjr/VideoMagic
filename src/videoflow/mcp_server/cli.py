"""``videoflow-mcp`` — stdio transport for local agents."""

from __future__ import annotations

from videoflow.mcp_server.server import build_server


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()
