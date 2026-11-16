"""Generate an OpenCode mcp.json block for VideoFlow modular servers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    "core": ["core"],
    "decupagem": ["core"],
    "broll": ["core", "fetch"],
    "audio": ["core", "audio"],
    "vision": ["core", "vision"],
    "full": ["core", "fetch", "audio", "vision"],
}


def server_block(name: str, *, prompts: bool = True) -> dict[str, object]:
    prompt_flag = [] if prompts else ["--no-prompts"]
    prompt_env = {} if prompts else {"VF_MCP_PROMPTS": "0"}
    if name == "core":
        return {
            "type": "local",
            "command": [
                "uv",
                "run",
                "--directory",
                str(ROOT),
                "videoflow-mcp",
                *prompt_flag,
            ],
            "environment": {"VF_WORKSPACE_ROOT": "${VF_WORKSPACE_ROOT}", **prompt_env},
        }
    package = {
        "fetch": "mcp-fetch",
        "audio": "mcp-audio",
        "vision": "mcp-vision",
    }[name]
    command = {
        "fetch": "videoflow-mcp-fetch",
        "audio": "videoflow-mcp-audio",
        "vision": "videoflow-mcp-vision",
    }[name]
    return {
        "type": "local",
        "command": [
            "uv",
            "run",
            "--project",
            str(ROOT / "packages" / package),
            command,
        ],
        "environment": {
            "VF_WORKSPACE_ROOT": "${VF_WORKSPACE_ROOT}",
            "VF_COMPUTE_MODE": "${VF_COMPUTE_MODE:-auto}",
            "VF_GPU_WORKER_URL": "${VF_GPU_WORKER_URL:-}",
            "VF_GPU_WORKER_TOKEN": "${VF_GPU_WORKER_TOKEN:-}",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=sorted(PROFILES), default="core")
    parser.add_argument("--output", default="")
    parser.add_argument(
        "--no-prompts",
        action="store_true",
        help="Do not register the three videoflow_* MCP prompts.",
    )
    args = parser.parse_args()
    servers = {
        name: server_block(name, prompts=not args.no_prompts) for name in PROFILES[args.profile]
    }
    payload = {"mcp": {"servers": servers}}
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
