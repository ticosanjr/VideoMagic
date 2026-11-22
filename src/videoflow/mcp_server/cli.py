"""``videoflow-mcp`` — stdio transport for local agents."""

from __future__ import annotations

import argparse
import os

from videoflow.application.jobs import JobManager
from videoflow.mcp_server.server import build_server
from videoflow.runtime import portable_home


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
    parser.add_argument(
        "--profile",
        choices=["core", "full"],
        default=os.environ.get("VF_MCP_PROFILE", "core"),
        help="Exact tool profile exposed over stdio.",
    )
    args = parser.parse_args(argv)
    manager = JobManager(store_dir=portable_home() / "jobs")
    build_server(
        manager,
        prompts=prompts_enabled(flag=args.no_prompts),
        profile=args.profile,
    ).run("stdio")


if __name__ == "__main__":
    main()
