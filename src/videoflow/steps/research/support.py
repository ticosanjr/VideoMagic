"""Pure research helpers, file writers, and fallbacks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from videoflow.application.search import SearchDocument, SearchResult
from videoflow.core.context import PipelineContext


def _slug(value: str, fallback: str = "agent") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-")
    return cleaned[:60] or fallback


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _case_source_urls(cases: list[dict[str, Any]]) -> set[str]:
    urls: set[str] = set()
    for case in cases:
        for source in case.get("sources", []):
            if isinstance(source, dict) and source.get("url"):
                urls.add(str(source["url"]))
    return urls


def _normalize_case(raw: dict[str, Any], allowed_urls: set[str]) -> dict[str, Any]:
    sources = []
    for source in raw.get("sources", []) if isinstance(raw.get("sources"), list) else []:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url") or "").strip()
        if not url:
            continue
        sources.append(
            {
                "url": url,
                "title": str(source.get("title") or url).strip(),
                "verified": url in allowed_urls,
            }
        )
    return {
        "title": str(raw.get("title") or "Untitled case").strip(),
        "summary": str(raw.get("summary") or "").strip(),
        "defense": str(raw.get("defense") or "").strip(),
        "published_at": str(raw.get("published_at") or "").strip(),
        "sources": sources,
        "source_count": len(sources),
    }


def _fallback_cases(
    scope: str,
    results: list[SearchResult],
    documents: list[SearchDocument],
    *,
    max_cases: int,
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    by_url = {document.url: document for document in documents}
    for result in results[:max_cases]:
        document = by_url.get(result.url)
        text = document.text if document is not None else result.snippet
        cases.append(
            {
                "title": result.title or scope,
                "summary": (text or result.snippet or "Source digest only.")[:4000],
                "defense": "",
                "published_at": result.published_at,
                "sources": [
                    {
                        "url": result.url,
                        "title": result.title or result.url,
                        "verified": True,
                    }
                ],
                "source_count": 1,
                "fallback": True,
            }
        )
    return cases


def _render_research_markdown(
    scope: str, topic: str, cases: list[dict[str, Any]], notes: str
) -> str:
    lines = [f"# Research — {scope}", "", f"**Topic:** {topic or '(not provided)'}", ""]
    if notes:
        lines.extend([f"**Coverage note:** {notes}", ""])
    for index, case in enumerate(cases, start=1):
        lines.append(f"## {index}. {case['title']}")
        lines.append("")
        if case.get("summary"):
            lines.extend([case["summary"], ""])
        if case.get("defense"):
            lines.extend([f"**Defense:** {case['defense']}", ""])
        if case.get("published_at"):
            lines.extend([f"**Published:** {case['published_at']}", ""])
        sources = case.get("sources") or []
        if sources:
            lines.append("**Sources:**")
            for source in sources:
                label = source.get("title") or source.get("url")
                status = "" if source.get("verified") else " *(unverified)*"
                lines.append(f"- [{label}]({source.get('url')}){status}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _read_agent_payloads(context: PipelineContext) -> list[dict[str, Any]]:
    directory = context.output / "research"
    payloads: list[dict[str, Any]] = []
    for path in sorted(directory.glob("agent_*.json")) if directory.is_dir() else []:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    revised = directory / "revised"
    for path in sorted(revised.glob("*.md")) if revised.is_dir() else []:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        payloads.append(
            {
                "agent_id": f"revised-{path.stem}",
                "label": f"Revised {path.stem}",
                "topic": "",
                "cases": [
                    {
                        "title": path.stem,
                        "summary": text[:20000],
                        "defense": "",
                        "published_at": "",
                        "sources": [],
                    }
                ],
                "sources": [],
                "generated_by": "human",
                "warning": "Human-supplied research has no machine-verifiable source manifest.",
            }
        )
    return payloads


def _read_master(context: PipelineContext) -> tuple[list[dict[str, Any]], str]:
    path = context.output / "research" / "master.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    cases = payload.get("cases") if isinstance(payload, dict) else []
    return (
        [item for item in cases if isinstance(item, dict)] if isinstance(cases, list) else [],
        str(payload.get("topic") or "") if isinstance(payload, dict) else "",
    )


def _fallback_script(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections = []
    for index, case in enumerate(cases, start=1):
        sections.append(
            {
                "id": index,
                "title": str(case.get("title") or f"Case {index}"),
                "narration": str(case.get("summary") or case.get("title") or ""),
                "visual": "Archive image or document highlight for this case.",
                "duration_sec": 30,
            }
        )
    return sections


def _render_script(sections: list[dict[str, Any]]) -> tuple[str, str]:
    narration = "\n\n".join(
        str(section.get("narration") or "").strip()
        for section in sections
        if str(section.get("narration") or "").strip()
    )
    lines = ["# Edition script", ""]
    for section in sections:
        index = section.get("id") or len(lines)
        lines.extend(
            [
                f"## {index}. {section.get('title') or 'Untitled'}",
                "",
                f"**Narration:** {section.get('narration') or ''}",
                "",
                f"**Visual:** {section.get('visual') or ''}",
                "",
                f"**Duration:** {section.get('duration_sec') or 30}s",
                "",
            ]
        )
    return narration.rstrip() + "\n", "\n".join(lines).rstrip() + "\n"

