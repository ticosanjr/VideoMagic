"""Scoped research agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from videoflow.application.search import (
    SearchDocument,
    SearchResult,
    fetch_documents,
    search_web,
    source_manifest,
)
from videoflow.application.settings import load_settings
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step
from videoflow.steps.research.params import ResearchParams
from videoflow.steps.research.prompts import DEFAULT_SCOPES, RESEARCH_PROMPT
from videoflow.steps.research.support import (
    _fallback_cases,
    _normalize_case,
    _render_research_markdown,
    _slug,
    _write_json,
    _write_text,
)


@register_step
class ResearchStep(BaseStep):
    type = "research.multi_agent"
    title = "Research agents"
    description = (
        "Run scoped research agents over local and free web providers, validate "
        "citations against the source manifest, and write one Markdown dossier per scope."
    )
    status = "available"
    icon = "⌕"
    color = "#a78bfa"
    params_model = ResearchParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ResearchParams.model_validate(params)
        answers = context.metadata.get("hilt_answers", {})
        answer_map = answers.get("answers", {}) if isinstance(answers, dict) else {}
        topic = (
            options.topic.strip()
            or str(context.metadata.get("variables", {}).get("topic") or "").strip()
            or str(answer_map.get("topic") or "").strip()
            or "Research directive"
        )
        temporal = str(answer_map.get("temporal_scope") or "").strip()
        if temporal and temporal not in topic:
            topic = f"{topic} — {temporal}"
        scopes = options.scopes or [item[2] for item in DEFAULT_SCOPES]
        names = options.scopes or [item[1] for item in DEFAULT_SCOPES]
        ids = options.scopes or [item[0] for item in DEFAULT_SCOPES]
        agents: list[dict[str, Any]] = []
        all_artifacts: list[Path] = []
        settings = load_settings()
        allow_external = (
            options.allow_external_services or settings.search.allow_network
        )
        for index, scope in enumerate(scopes):
            label = names[index] if index < len(names) else f"Agent {index + 1}"
            agent_id = _slug(ids[index] if index < len(ids) else f"agent-{index + 1}")
            query = f"{topic} {scope}".strip()
            io.report(
                int(index / max(1, len(scopes)) * 100),
                f"Researching {label}",
            )
            results: list[SearchResult] = []
            documents: list[SearchDocument] = []
            warning = ""
            try:
                results = search_web(
                    query,
                    settings=settings,
                    providers=options.search_providers or None,
                    allow_external_services=allow_external,
                    allowed_external_hosts=options.allowed_external_hosts,
                    limit=options.max_results,
                )
                documents = fetch_documents(
                    results,
                    settings,
                    limit=options.fetch_pages,
                    allow_external_services=allow_external,
                    allowed_external_hosts=options.allowed_external_hosts,
                )
            except Exception as exc:  # noqa: BLE001 - review gate handles the gap
                warning = f"Search failed: {exc}"
                context.warnings.append(f"{label}: {warning}")
            manifest = source_manifest(results, documents)
            allowed_urls = {item["url"] for item in manifest}
            cases: list[dict[str, Any]] = []
            notes = ""
            generated_by = "manifest"
            if io.llm_client is not None and (results or documents):
                document_text = "\n\n".join(
                    f"URL: {document.url}\nTITLE: {document.title}\n{document.text[:6000]}"
                    for document in documents
                )
                prompt = RESEARCH_PROMPT.format(
                    topic=topic,
                    scope=scope,
                    language=options.language,
                    manifest=json.dumps(manifest, ensure_ascii=False)[:20000],
                    documents=document_text[:24000] or "(no fetched text)",
                )
                try:
                    payload = io.llm_client.complete_json(
                        prompt, "videoflow.research"
                    )
                    raw_cases = payload.get("cases") if isinstance(payload, dict) else []
                    if isinstance(raw_cases, list):
                        cases = [
                            _normalize_case(item, allowed_urls)
                            for item in raw_cases[: options.max_cases]
                            if isinstance(item, dict)
                        ]
                    notes = str(payload.get("notes") or "") if isinstance(payload, dict) else ""
                    generated_by = "llm"
                except Exception as exc:  # noqa: BLE001 - keep the deterministic digest
                    warning = f"Research model fallback: {exc}"
                    context.warnings.append(f"{label}: {warning}")
            if not cases:
                cases = _fallback_cases(
                    label, results, documents, max_cases=options.max_cases
                )
            unverified = sum(
                1
                for case in cases
                for source in case.get("sources", [])
                if not source.get("verified")
            )
            payload = {
                "agent_id": agent_id,
                "label": label,
                "scope": scope,
                "topic": topic,
                "cases": cases,
                "sources": manifest,
                "notes": notes,
                "generated_by": generated_by,
                "warning": warning,
                "unverified_sources": unverified,
            }
            json_path = context.output / "research" / f"agent_{agent_id}.json"
            markdown_path = context.output / "research" / f"agent_{agent_id}.md"
            _write_json(json_path, payload)
            _write_text(
                markdown_path,
                _render_research_markdown(label, topic, cases, notes),
            )
            all_artifacts.extend([json_path, markdown_path])
            agents.append(payload)
            context.artifacts[f"research_{agent_id}"] = str(markdown_path)
        context.metadata["research_agents"] = agents
        context.artifacts["research_agents"] = str(
            context.output / "research" / "agents.json"
        )
        _write_json(context.output / "research" / "agents.json", {"agents": agents})
        context.hashes["research.multi_agent"] = digest_payload(
            {"agents": [item["agent_id"] for item in agents], "topic": topic}
        )
        io.report(100, f"{len(agents)} research agent(s) finished")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(value)
            for key, value in context.artifacts.items()
            if key.startswith("research_")
        )

