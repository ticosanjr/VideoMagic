from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from videoflow.application.shorts import ShortClip
from videoflow.core.context import PipelineContext
from videoflow.domain.state import Sentence
from videoflow.steps.base import StepIO
from videoflow.steps.shorts_score import ShortsScoreStep


def test_llm_score_merges_with_heuristic(tmp_path: Path) -> None:
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        transcript=[
            Sentence(id=1, start_sample=0, end_sample=48000, text="Hook here."),
            Sentence(id=2, start_sample=48000, end_sample=96000, text="Payoff 3x."),
        ],
    )
    clip = ShortClip(
        title="Hook here. Payoff 3x.",
        start_sample=0,
        end_sample=96000,
        sentence_ids=(1, 2),
        pieces=((0, 96000),),
        virality_score=60.0,
        score_breakdown=(("markers", 10.0),),
    )

    class FakeAi:
        def complete_json(self, *args, **kwargs):
            return SimpleNamespace(
                data={
                    "score": 80,
                    "arc": "climax",
                    "justification": "clear payoff",
                }
            )

    updated = ShortsScoreStep()._llm_score(
        [clip], context, StepIO(ai=FakeAi()), "hybrid"
    )
    assert updated[0].virality_score == 70.0
    assert updated[0].arc == "climax"
    assert updated[0].curation_source == "hybrid"
    assert ("llm", 80.0) in updated[0].score_breakdown
