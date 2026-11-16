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


def server_block(name: str) -> dict[str, object]:
    if name == "core":
        return {
            "type": "local",
            "command": ["uv", "run", "--directory", str(ROOT), "videoflow-mcp"],
            "environment": {"VF_WORKSPACE_ROOT": "${VF_WORKSPACE_ROOT}"},
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
    args = parser.parse_args()
    servers = {name: server_block(name) for name in PROFILES[args.profile]}
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
