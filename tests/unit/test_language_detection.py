from videoflow.application.language import detect_text_language


def test_detects_portuguese_with_stopwords() -> None:
    language, confidence = detect_text_language(
        "Olá pessoal, hoje a gente vai falar sobre o que é isso aqui e como funciona."
    )
    assert language == "pt"
    assert confidence > 0.5


def test_detects_english_with_stopwords() -> None:
    language, confidence = detect_text_language(
        "Hello everyone, today we are going to talk about the things that you can do with this."
    )
    assert language == "en"
    assert confidence > 0.5


def test_ambiguous_or_short_text_does_not_guess() -> None:
    assert detect_text_language("ok") == ("", 0.0)
    assert detect_text_language("one two three four five six seven eight") == ("", 0.0)


def test_langdetect_is_preferred_when_installed(monkeypatch) -> None:
    import sys
    from types import ModuleType, SimpleNamespace

    module = ModuleType("langdetect")
    module.detect_langs = lambda text: [SimpleNamespace(lang="it", prob=0.88)]  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langdetect", module)

    assert detect_text_language("questo è un testo abbastanza longo per la lingua") == (
        "it",
        0.88,
    )


def test_record_language_persists_state_and_artifact(tmp_path) -> None:
    from videoflow.core.context import PipelineContext
    from videoflow.domain.state import ProjectState
    from videoflow.steps.transcribe import _record_language

    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        state=ProjectState(),
        transcript=[],
    )
    _record_language(context, "en", 0.91, source="test")

    assert context.transcript_language == "en"
    assert context.state.language == "en"
    assert context.state.language_confidence == 0.91
    assert (tmp_path / "out" / "transcript" / "language.json").is_file()
