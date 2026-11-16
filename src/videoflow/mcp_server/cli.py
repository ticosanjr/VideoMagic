"""``videoflow-mcp`` — stdio transport for local agents."""

from __future__ import annotations

import argparse
import os

from videoflow.mcp_server.server import build_server


def prompts_enabled(*, flag: bool = False) -> bool:
    """Resolve prompt registration from ``--no-prompts`` and the environment."""

    if flag:
        return False
    raw = os.environ.get("VF_MCP_PROMPTS", "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="videoflow-mcp")
    parser.add_argument(
        "--no-prompts",
        action="store_true",
        help="Register tools and resources without the videoflow_* prompts.",
    )
    args = parser.parse_args(argv)
    build_server(prompts=prompts_enabled(flag=args.no_prompts)).run("stdio")


if __name__ == "__main__":
    main()
