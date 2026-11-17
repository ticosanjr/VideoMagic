"""Generate an OpenCode mcp.json block for VideoFlow modular servers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from videoflow.application.opencode_config import PROFILES, build_config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=sorted(PROFILES), default="core")
    parser.add_argument("--output", default="")
    parser.add_argument(
        "--workspace-root",
        default="${VF_WORKSPACE_ROOT}",
        help="Value written to VF_WORKSPACE_ROOT in each server block.",
    )
    parser.add_argument(
        "--no-prompts",
        action="store_true",
        help="Do not register the three videoflow_* MCP prompts.",
    )
    args = parser.parse_args()
    payload = build_config(
        args.profile,
        workspace_root=args.workspace_root,
        prompts=not args.no_prompts,
    )
    text = json.dumps(payload, indent=2) + "\n"
    if args.output:
        target = Path(args.output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
