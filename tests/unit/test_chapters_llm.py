from __future__ import annotations

from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, Sentence
from videoflow.steps.base import StepIO
from videoflow.steps.delivery_qa import ChaptersParams, ChaptersStep


class FakeLlm:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete_json(self, prompt: str, schema: str):
        self.prompts.append(prompt)
        return {"titles": ["Opening", "Payoff"]}


def _context(tmp_path: Path) -> PipelineContext:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    return PipelineContext(
        source=source,
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        media=MediaInfo(
            source_path=str(source),
            duration_frames=60,
            fps_num=30,
            fps_den=1,
            width=640,
            height=360,
            audio_sample_rate=48000,
        ),
        transcript=[
            Sentence(id=1, start_sample=0, end_sample=48000, text="First beat."),
            Sentence(id=2, start_sample=48000, end_sample=96000, text="Second beat."),
        ],
    )


def test_chapter_titles_use_llm_when_enabled(tmp_path: Path) -> None:
    llm = FakeLlm()
    context = _context(tmp_path)
    context.output.mkdir(parents=True, exist_ok=True)
    ChaptersStep().run(
        context,
        ChaptersParams(max_chapters=2, use_llm=True),
        StepIO(llm_client=llm),
    )
    assert llm.prompts
    assert context.artifacts["chapters"]
    payload = Path(context.artifacts["chapters"]).read_text()
    assert "Opening" in payload
