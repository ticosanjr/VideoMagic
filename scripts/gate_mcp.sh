#!/usr/bin/env bash
# MCP-only release gate: registry, server, tools, resources, docs, and compositors.
#
#   ./scripts/gate_mcp.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== ruff =="
uv run ruff check src tests scripts

echo "== registry and server surface =="
uv run python - <<'PY'
import asyncio

from videoflow.mcp_server.registry import RESOURCE_SPECS, TOOL_SPECS
from videoflow.mcp_server.server import build_server

names = [spec.name for spec in TOOL_SPECS]
assert len(names) == 44, names
assert len(names) == len(set(names))
assert all(name.startswith("vf_") for name in names)
assert len(RESOURCE_SPECS) == 16
registered = sorted(tool.name for tool in asyncio.run(build_server().list_tools()))
assert registered == sorted(names), (registered, names)
print(f"core tools: {len(names)}; resources: {len(RESOURCE_SPECS)}")
PY

echo "== MCP tests and coverage =="
uv run coverage run --rcfile=/dev/null -m pytest \
  tests/unit/test_agent_helpers_recipe_scrub.py \
  tests/unit/test_agent_mcp.py \
  tests/unit/test_agent_resources_coverage.py \
  tests/unit/test_agent_tools_coverage.py \
  tests/unit/test_alignment_forced.py \
  tests/unit/test_asr_remote.py \
  tests/unit/test_audio_events_yamnet.py \
  tests/unit/test_compute_plan.py \
  tests/unit/test_output_layout.py \
  tests/unit/test_scene_contracts.py \
  tests/unit/test_scene_intel.py \
  tests/unit/test_formats.py \
  tests/unit/test_system_folder_picker.py \
  tests/unit/test_api_styles.py \
  tests/unit/test_api_workflows.py \
  tests/unit/test_scene_mcp.py \
  tests/unit/test_short_composition.py \
  tests/unit/test_short_captions.py \
  tests/unit/test_short_plan_step.py \
  tests/unit/test_short_render.py \
  tests/unit/test_short_export.py \
  tests/unit/test_bootstrap_opencode.py \
  tests/unit/test_compositor.py \
  tests/unit/test_contracts_docs.py \
  tests/unit/test_core_tools.py \
  tests/unit/test_decupage_benchmark.py \
  tests/unit/test_decupage_review.py \
  tests/unit/test_decupage_snap.py \
  tests/unit/test_speech_asu.py \
  tests/unit/test_gpu_preflight_tool.py \
  tests/unit/test_gpu_capabilities.py \
  tests/unit/test_headless_mcp.py \
  tests/unit/test_domain_audio_vision_tools.py \
  tests/unit/test_mcp_cli.py \
  tests/unit/test_mcp_domain_cli.py \
  tests/unit/test_mcp_fetch.py \
  tests/unit/test_mcp_server_guard.py \
  tests/unit/test_qa_short_aware_tool.py \
  tests/unit/test_wave4_tools.py \
  tests/unit/test_wave_32.py \
  tests/unit/test_wave_32_captions.py \
  tests/unit/test_wave_32_extra.py \
  tests/unit/test_wave_32_shorts.py \
  tests/unit/test_wave_a_edges.py \
  tests/unit/test_wave_a_pipeline.py \
  tests/unit/test_wave_b.py \
  tests/unit/test_wave_c.py \
  tests/unit/test_wave_d.py \
  tests/contract/test_mcp.py \
  tests/contract/test_acceptance_3_3.py \
  -m "not media" -q --no-header -o addopts=""

uv run coverage report \
  --include='src/videoflow/mcp_server/*' \
  --fail-under=80

echo "== decupage benchmark =="
uv run python scripts/decupage_benchmark.py --self-test --require-thresholds >/dev/null

echo "gate: MCP checks passed"
