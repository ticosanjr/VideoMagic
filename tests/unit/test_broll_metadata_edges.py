from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from videoflow.application import metadata_llm
from videoflow.application.intelligence.models import IntelligenceError
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError
from videoflow.steps import broll_generate
from videoflow.steps.base import StepIO
from videoflow.steps.broll_generate import GenerateBrollParams, GenerateBrollStep


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    output.mkdir(parents=True)
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )


def test_prompt_for_uses_titles_and_entities() -> None:
    context = SimpleNamespace(
        selected_shorts=[SimpleNamespace(title="Short one")],
        metadata={
            "narrative_beats": [
                "bad",
                {"extracted_entities": "bad"},
                {
                    "extracted_entities": {
                        "people": [
                            "bad",
                            {"canonical_name": "Alice"},
                            {"raw_mention": "Alice"},
                        ],
                        "physical_objects": [{"object": "document"}],
                        "locations": [{"location_name": "Paris"}],
                    }
                },
            ]
        },
    )
    prompt = broll_generate._prompt_for(context, "")
    assert "Short one" in prompt
    assert "Alice" in prompt
    assert "document" in prompt
    assert broll_generate._prompt_for(context, "  custom ") == "custom"
    empty = SimpleNamespace(selected_shorts=[], metadata={})
    assert "editorial b-roll" in broll_generate._prompt_for(empty, "")


def test_generate_broll_skips_without_endpoint(tmp_path: Path) -> None:
    context = _context(tmp_path)
    GenerateBrollStep().run(context, GenerateBrollParams(), StepIO())
    assert any("no image endpoint" in item for item in context.warnings)


def test_generate_broll_openai_success_and_failures(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    saved = tmp_path / "generated.png"
    saved.write_bytes(b"png")
    calls: list[dict] = []

    monkeypatch.setattr(
        broll_generate,
        "generate_openai_image",
        lambda *args, **kwargs: calls.append(kwargs) or b"png",
    )
    monkeypatch.setattr(
        broll_generate,
        "save_image",
        lambda name, data: {"file": saved, "name": name, "sha256": "hash"},
    )
    monkeypatch.setattr(broll_generate, "images_dir", lambda: tmp_path)
    monkeypatch.setattr(
        broll_generate, "scan_directory", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        broll_generate.GenerateBrollStep,
        "_write_ledger",
        staticmethod(lambda output, generated: None),
    )
    GenerateBrollStep().run(
        context,
        GenerateBrollParams(
            base_url="http://127.0.0.1:1/v1",
            count=2,
            seed=5,
            negative_prompt="no text",
        ),
        StepIO(),
    )
    assert context.metadata["generated_broll"]
    assert calls[0]["seed"] == 5
    assert calls[1]["seed"] == 6
    assert "generated_broll" in context.artifacts

    context = _context(tmp_path / "failed")
    monkeypatch.setattr(
        broll_generate,
        "generate_openai_image",
        lambda *args, **kwargs: (_ for _ in ()).throw(IngestError("no endpoint")),
    )
    GenerateBrollStep().run(
        context,
        GenerateBrollParams(base_url="http://127.0.0.1:1/v1"),
        StepIO(),
    )
    assert any("B-roll generation failed" in item for item in context.warnings)
    assert any("produced no images" in item for item in context.warnings)


def test_generate_broll_opencode_provider(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    monkeypatch.setattr(
        broll_generate,
        "build_intelligence",
        lambda: SimpleNamespace(generate_image=lambda *args, **kwargs: [b"image"]),
    )
    monkeypatch.setattr(
        broll_generate,
        "save_image",
        lambda name, data: {"file": tmp_path / name, "name": name, "sha256": ""},
    )
    monkeypatch.setattr(broll_generate, "images_dir", lambda: tmp_path)
    monkeypatch.setattr(
        broll_generate, "scan_directory", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        broll_generate.GenerateBrollStep,
        "_write_ledger",
        staticmethod(lambda output, generated: None),
    )
    GenerateBrollStep().run(
        context, GenerateBrollParams(provider="opencode_v2"), StepIO()
    )
    assert context.metadata["generated_broll"][0]["provider"] == "generated"

    context = _context(tmp_path / "error")
    monkeypatch.setattr(
        broll_generate,
        "build_intelligence",
        lambda: SimpleNamespace(
            generate_image=lambda *args, **kwargs: (_ for _ in ()).throw(
                IntelligenceError("model down")
            )
        ),
    )
    GenerateBrollStep().run(
        context, GenerateBrollParams(provider="opencode_v2"), StepIO()
    )
    assert any("B-roll generation failed" in item for item in context.warnings)


def test_metadata_llm_validation_and_fallback() -> None:
    with pytest.raises(ValueError, match="title"):
        metadata_llm._validate({"title": "", "description": "x"}, "youtube")
    with pytest.raises(ValueError, match="description"):
        metadata_llm._validate({"title": "x", "description": ""}, "youtube")
    cleaned = metadata_llm._validate(
        {
            "title": "t" * 200,
            "description": "d" * 6000,
            "hashtags": ["#a", "", 3],
        },
        "youtube",
    )
    assert len(cleaned["title"]) == 100
    assert cleaned["hashtags"] == ["#a", "3"]

    with pytest.raises(ValueError, match="Unsupported platform"):
        metadata_llm.generate_metadata_with_llm(
            SimpleNamespace(), "text", platform="myspace"
        )

    class Client:
        def complete_json(self, schema, prompt, name, validator=None):
            payload = {
                "title": "Hook",
                "description": "Payoff",
                "hashtags": ["#one"],
            }
            assert validator is not None
            validator(payload)
            return SimpleNamespace(data=payload)

    result = metadata_llm.generate_metadata_with_llm(
        Client(),
        "text",
        title="Title",
        extra_hashtags=("#one", "#two"),
    )
    assert result.hashtags == ("#one", "#two")
    assert result.title == "Hook"

    class Broken:
        def complete_json(self, *args, **kwargs):
            raise IntelligenceError("down")

    fallback = metadata_llm.generate_metadata_with_llm(
        Broken(), "This is a sentence about a documentary."
    )
    assert fallback.title


def test_semantic_model_loading_paths(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import semantic

    monkeypatch.setattr(
        semantic.Path, "home", classmethod(lambda cls: tmp_path)
    )
    monkeypatch.delenv("VIDEOFLOW_EMBEDDING_MODEL", raising=False)
    assert semantic.model_path() is None
    default = (
        tmp_path
        / ".videoflow"
        / "models"
        / "embeddings"
        / "paraphrase-multilingual-MiniLM-L12-v2"
    )
    default.mkdir(parents=True)
    (default / "config.json").write_text("{}")
    assert semantic.model_path() == default

    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    assert semantic.available() is False

    class Model:
        def encode(self, texts, **kwargs):
            if texts == ["boom"]:
                raise RuntimeError("bad input")
            return [[1.0, 0.0] for _ in texts]

    module = ModuleType("sentence_transformers")
    module.SentenceTransformer = lambda path: Model()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    assert semantic.available() is True
    semantic._MODEL = None
    semantic._MODEL_PATH = None
    model = semantic._load()
    assert model is not None
    assert semantic._load() is model
    assert semantic.encode(["boom"]) is None
    assert semantic.encode([]).shape == (0, 0)

    monkeypatch.setenv("VIDEOFLOW_EMBEDDING_MODEL", str(tmp_path / "missing"))
    assert semantic.model_path() is None
    assert semantic._load() is None

    broken = ModuleType("sentence_transformers")
    broken.SentenceTransformer = lambda path: (_ for _ in ()).throw(  # type: ignore[attr-defined]
        RuntimeError("load failed")
    )
    monkeypatch.setitem(sys.modules, "sentence_transformers", broken)
    semantic._MODEL = None
    semantic._MODEL_PATH = None
    assert semantic._load() is None
