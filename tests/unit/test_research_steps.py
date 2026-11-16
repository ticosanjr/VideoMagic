from __future__ import annotations

import json
from pathlib import Path

from videoflow.application.settings import AppSettings, SearchSettings
from videoflow.core.context import PipelineContext
from videoflow.steps.base import StepIO
from videoflow.steps.research import (
    ConsolidateParams,
    ConsolidateStep,
    DualScriptStep,
    PresenterParams,
    PresenterProfileStep,
    ResearchParams,
    ResearchStep,
    ScriptParams,
)


class FakeLlm:
    def __init__(self, source_url: str = "") -> None:
        self.source_url = source_url

    def complete_json(self, prompt: str, schema_name: str) -> dict:
        if schema_name == "videoflow.research":
            return {
                "cases": [
                    {
                        "title": "Guaruja triplex",
                        "summary": "Court records describe the property.",
                        "defense": "The defense denied ownership.",
                        "published_at": "2016-03-01",
                        "sources": [{"url": self.source_url, "title": "Court record"}],
                    }
                ],
                "notes": "one case",
            }
        if schema_name == "videoflow.research.master":
            return {
                "cases": [
                    {
                        "title": "Guaruja triplex",
                        "summary": "Merged court narrative.",
                        "defense": "The defense denied ownership.",
                        "published_at": "2016-03-01",
                        "sources": [{"url": self.source_url, "title": "Court record"}],
                    }
                ],
                "notes": "merged",
            }
        if schema_name == "videoflow.script":
            return {
                "sections": [
                    {
                        "id": 1,
                        "title": "The property",
                        "narration": "The court records describe the property.",
                        "visual": "Document highlight on the deed.",
                        "duration_sec": 45,
                    }
                ],
                "notes": "script",
            }
        return {}


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )


def test_research_consolidate_and_script(tmp_path: Path, monkeypatch) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    source = corpus / "case.md"
    source.write_text(
        "# Guaruja triplex\n\nCourt records describe a corruption investigation.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "videoflow.steps.research.agent.load_settings",
        lambda: AppSettings(
            search=SearchSettings(
                local_paths=[str(corpus)],
                providers=["local"],
                max_results=5,
                fetch_pages=2,
            )
        ),
    )
    source_url = source.resolve().as_uri()
    context = _context(tmp_path)
    io = StepIO(llm_client=FakeLlm(source_url))
    ResearchStep().run(
        context,
        ResearchParams(topic="corruption", scopes=["corruption court"]),
        io,
    )
    agents = context.metadata["research_agents"]
    assert agents[0]["cases"][0]["sources"][0]["verified"] is True
    assert (context.output / "research" / "agents.json").is_file()

    ConsolidateStep().run(context, ConsolidateParams(), io)
    assert context.metadata["research_master"]["case_count"] == 1
    assert (context.output / "research" / "master.md").is_file()

    DualScriptStep().run(context, ScriptParams(target_words=300), io)
    assert (context.output / "script" / "narration.txt").is_file()
    assert "The court records" in (context.output / "script" / "narration.txt").read_text(
        encoding="utf-8"
    )
    assert "Document highlight" in (context.output / "script" / "edition.md").read_text(
        encoding="utf-8"
    )


def test_research_and_script_fallbacks_without_llm(tmp_path: Path, monkeypatch) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "case.md").write_text("Corruption court record.", encoding="utf-8")
    monkeypatch.setattr(
        "videoflow.steps.research.agent.load_settings",
        lambda: AppSettings(
            search=SearchSettings(local_paths=[str(corpus)], providers=["local"], fetch_pages=1)
        ),
    )
    context = _context(tmp_path)
    ResearchStep().run(
        context,
        ResearchParams(topic="corruption", scopes=["corruption"]),
        StepIO(),
    )
    assert context.metadata["research_agents"][0]["generated_by"] == "manifest"
    ConsolidateStep().run(context, ConsolidateParams(), StepIO())
    DualScriptStep().run(context, ScriptParams(), StepIO())
    script = json.loads((context.output / "script" / "script.json").read_text(encoding="utf-8"))
    assert script["generated_by"] == "fallback"
    assert script["sections"]


def test_presenter_profile_from_transcript(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.metadata["transcript_text"] = ""
    from videoflow.domain.state import Sentence

    context.transcript = [
        Sentence(id=1, start_sample=0, end_sample=4800, text="A short sentence."),
        Sentence(id=2, start_sample=4800, end_sample=9600, text="Another clear sentence."),
    ]
    PresenterProfileStep().run(context, PresenterParams(), StepIO())
    profile = context.metadata["presenter_profile"]
    assert profile["sentence_count"] == 2
    assert profile["word_count"] > 0
    assert (context.output / "research" / "presenter-profile.md").is_file()


def test_consolidate_merges_duplicates_and_requires_sources(tmp_path: Path) -> None:
    context = _context(tmp_path)
    research = context.output / "research"
    research.mkdir(parents=True)
    (research / "agent_a.json").write_text(
        json.dumps(
            {
                "topic": "topic",
                "cases": [
                    "bad",
                    {
                        "title": "Case One",
                        "summary": "short",
                        "sources": [{"url": "https://a"}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (research / "agent_b.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "title": " case   one ",
                        "summary": "a much longer summary",
                        "defense": "denied",
                        "sources": [
                            {"url": "https://a"},
                            {"url": "https://b"},
                        ],
                    },
                    {"title": "No source", "summary": "text"},
                ]
            }
        ),
        encoding="utf-8",
    )

    ConsolidateStep().run(context, ConsolidateParams(require_sources=True), StepIO())

    master = context.metadata["research_master"]
    assert master["agent_count"] == 2
    assert master["case_count"] == 2
    merged = master["cases"][0]
    assert merged["summary"] == "a much longer summary"
    assert merged["defense"] == "denied"
    assert len(merged["sources"]) == 2
    assert any("no source" in warning for warning in master["warnings"])
    assert ConsolidateStep().cache_outputs(context)


def test_consolidate_llm_failure_keeps_deterministic_merge(tmp_path: Path) -> None:
    class BrokenLlm:
        def complete_json(self, prompt: str, schema_name: str) -> dict:
            raise RuntimeError("offline")

    context = _context(tmp_path)
    research = context.output / "research"
    research.mkdir(parents=True)
    (research / "agent_a.json").write_text(
        json.dumps({"cases": [{"title": "One", "summary": "x"}]}),
        encoding="utf-8",
    )
    ConsolidateStep().run(context, ConsolidateParams(), StepIO(llm_client=BrokenLlm()))
    assert context.metadata["research_master"]["generated_by"] == "deterministic"
    assert any("offline" in warning for warning in context.metadata["research_master"]["warnings"])


def test_research_support_handles_malformed_inputs(tmp_path: Path) -> None:
    from videoflow.steps.research.support import (
        _case_source_urls,
        _fallback_script,
        _normalize_case,
        _read_agent_payloads,
        _read_master,
        _render_script,
        _slug,
    )

    assert _slug("", "fallback") == "fallback"
    assert _case_source_urls(
        [
            {"sources": [{"url": "a"}, "bad", {"url": ""}]},
            {"sources": "bad"},
        ]
    ) == {"a"}
    normalized = _normalize_case(
        {
            "title": "",
            "sources": [{"url": ""}, "bad", {"url": "a"}],
        },
        {"a"},
    )
    assert normalized["title"] == "Untitled case"
    assert normalized["sources"][0]["verified"] is True

    context = _context(tmp_path)
    research = context.output / "research"
    revised = research / "revised"
    revised.mkdir(parents=True)
    (research / "agent_bad.json").write_text("{", encoding="utf-8")
    (revised / "human.md").write_text("Human notes", encoding="utf-8")
    (revised / "unreadable.md").mkdir()
    payloads = _read_agent_payloads(context)
    assert payloads[0]["generated_by"] == "human"
    assert payloads[0]["cases"][0]["title"] == "human"

    assert _read_master(context) == ([], "")
    (research / "master.json").write_text("[]", encoding="utf-8")
    assert _read_master(context) == ([], "")

    sections = _fallback_script([{}])
    assert sections[0]["title"] == "Case 1"
    narration, markdown = _render_script(
        [{"id": 0, "narration": " ", "title": "", "visual": "", "duration_sec": 0}]
    )
    assert narration.strip() == ""
    assert "Untitled" in markdown
