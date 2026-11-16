#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for package in vf-contracts vf-compute mcp-fetch mcp-audio mcp-vision gpu-worker; do
  echo "==> $package"
  uv sync --project "$ROOT/packages/$package" --quiet
done
echo "MCP server environments ready."
