"""MCP prompts, resources, and preset payloads."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from videoflow.domain.transcript import format_srt
from videoflow.mcp_server.context import ToolContext, error

PRESET_OPTIONS: dict[str, dict[str, Any]] = {
    "youtube-talking-head": {
        "jcut": True,
        "zooms": True,
        "noise_db": -30.0,
        "min_silence_ms": 400,
    },
    "shorts-aggressive": {
        "jcut": True,
        "zooms": True,
        "noise_db": -30.0,
        "min_silence_ms": 250,
    },
    "lecture-clean": {
        "jcut": False,
        "zooms": False,
        "noise_db": -30.0,
        "min_silence_ms": 700,
    },
}


def presets_payload() -> dict[str, object]:
    presets: dict[str, object] = {
        name: {"source": "builtin", "overrides": options}
        for name, options in PRESET_OPTIONS.items()
    }
    try:
        directory = files("videoflow").joinpath("presets")
        for item in directory.iterdir():
            if item.name.endswith(".json"):
                presets[item.name] = {
                    "source": "shipped",
                    "preset": json.loads(item.read_text(encoding="utf-8")),
                }
    except (OSError, ValueError, TypeError):
        pass
    return {"ok": True, "presets": presets}


def register_prompts_resources(mcp: Any, ctx: ToolContext) -> None:
    """Register every MCP prompt and resource."""

    last = ctx.last

    @mcp.prompt(
        name="videoflow_produce",
        description="Run a recipe end to end and report artifacts.",
    )
    def produce_prompt(
        source: str, output: str, recipe_id: str = "youtube_talking_head"
    ) -> str:
        """ Produce a project from source media. """

        return (
            "Use the VideoFlow MCP tools. Run recipe "
            f"{recipe_id} for {source} with output {output}; poll the job, then "
            "summarize status, artifacts, warnings, and the next action."
        )

    @mcp.prompt(
        name="videoflow_review",
        description="Review the latest run and apply validated Copilot edits.",
    )
    def review_prompt(job_id: str, instruction: str) -> str:
        """ Review and improve a finished run. """

        return (
            f"Read job {job_id} and its timeline. Propose timeline edits for: "
            f"{instruction}. Show the diff, apply only validated edits, then "
            "validate the NLE exports."
        )

    @mcp.prompt(
        name="videoflow_deliver",
        description="Build and verify the delivery package.",
    )
    def deliver_prompt(job_id: str) -> str:
        """ Verify delivery artifacts for a job. """

        return (
            f"For job {job_id}, validate FCPXML/XMEML/Kdenlive, list artifacts and "
            "licenses, and report anything missing before hand-off."
        )

    @mcp.resource("videoflow://project/state")
    def project_state() -> str:
        """Current TimelineProjectState JSON."""

        state = ctx.project_state()
        if state is None:
            return json.dumps(
                error(
                    "state_not_found",
                    "Run a recipe and wait for the job to succeed first.",
                )
            )
        return state.model_dump_json(indent=2)

    @mcp.resource("videoflow://project/transcript")
    def project_transcript() -> str:
        """Plain transcript text or SRT."""

        transcript = ctx.transcript_for()
        if transcript is None:
            return json.dumps(
                error(
                    "transcript_not_found",
                    "Run a recipe with a transcribe step first.",
                )
            )
        state = ctx.project_state()
        return format_srt(transcript, ctx.sample_rate(state))

    @mcp.resource("videoflow://docs/integrations")
    def integrations_doc() -> str:
        """How to connect VideoFlow MCP to OpenCode or Paperclip with DeepSeek."""

        return json.dumps(
            {
                "ok": True,
                "mcp": {
                    "stdio": "videoflow-mcp",
                    "http": "http://127.0.0.1:8765/mcp/",
                },
                "opencode": {
                    "local": "opencode mcp add videoflow -- uv run videoflow-mcp",
                    "remote": (
                        "opencode mcp add videoflow --url "
                        "http://127.0.0.1:8765/mcp/"
                    ),
                    "model": "deepseek/deepseek-flash",
                },
                "paperclip": {
                    "mcp_url": "http://127.0.0.1:8765/mcp/",
                    "model": "DeepSeek adapter (deepseek-chat)",
                },
                "workflow": [
                    "videoflow_list_recipes",
                    "videoflow_run_recipe",
                    "videoflow_get_job",
                    "videoflow_get_timeline",
                    "videoflow_copilot_timeline",
                    "videoflow_validate_exports",
                ],
                "docs": "docs/integrations.md",
            },
            indent=2,
        )

    @mcp.resource("videoflow://presets/list")
    def presets_list() -> str:
        """Shipped and operator presets."""

        return json.dumps(presets_payload(), indent=2)

    @mcp.resource("videoflow://project/exports")
    def project_exports() -> str:
        """Paths of the latest export artifacts."""

        output = last.get("output")
        if not isinstance(output, Path):
            return json.dumps(
                error(
                    "exports_not_found",
                    "Run a recipe with videoflow_run_recipe first.",
                )
            )
        run_path = output / "run.json"
        if not run_path.is_file():
            return json.dumps(
                error(
                    "exports_not_found",
                    "The last job has not written a report yet.",
                )
            )
        try:
            report = json.loads(run_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return json.dumps(error("exports_unreadable", str(exc)))
        artifacts = report.get("artifacts", {})
        return json.dumps(
            {
                "ok": True,
                "output": str(output),
                "exports": {
                    name: {"path": path, "exists": Path(path).is_file()}
                    for name, path in artifacts.items()
                },
            },
            indent=2,
        )
