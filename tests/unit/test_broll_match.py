"""Shot-aware B-roll matching and the license report."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.application.shorts import ShortClip
from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, Sentence
from videoflow.steps.assets_intel import AssetMatchStep, MatchParams
from videoflow.steps.base import StepIO


def context(tmp_path: Path) -> PipelineContext:
    media = MediaInfo(
        source_path=str(tmp_path / "source.mp4"),
        duration_frames=100,
        fps_num=25,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=1000,
    )
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        media=media,
        transcript=[
            Sentence(id=0, start_sample=0, end_sample=5000, text="cidade ao amanhecer"),
            Sentence(
                id=1,
                start_sample=5000,
                end_sample=10000,
                text="pessoa trabalhando no escritorio",
            ),
        ],
        selected_shorts=[
            ShortClip(
                title="Rotina produtiva",
                start_sample=0,
                end_sample=10000,
                sentence_ids=(0, 1),
                pieces=((0, 10000),),
                score=12.0,
            )
        ],
        metadata={
            "scenes": [
                {"id": "shot-1", "start_sample": 0, "end_sample": 5000},
                {"id": "shot-2", "start_sample": 5000, "end_sample": 10000},
            ]
        },
    )


def test_match_uses_shots_and_writes_licenses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assets = [
        {
            "id": "a1",
            "name": "city sunrise aerial",
            "kind": "video",
            "path": "/a1.mp4",
            "tags": [],
            "license": "CC0",
        },
        {
            "id": "a2",
            "name": "office desk worker",
            "kind": "video",
            "path": "/a2.mp4",
            "tags": [],
            "license": "CC-BY",
        },
    ]
    monkeypatch.setattr(
        "videoflow.steps.assets_match.list_assets", lambda limit=2000: assets
    )
    ctx = context(tmp_path)

    AssetMatchStep().run(ctx, MatchParams(max_per_short=2, min_score=0.0), StepIO(stage="broll"))

    entries = ctx.metadata["broll_plan"]["Rotina produtiva"]
    assert [entry["shot_id"] for entry in entries] == ["shot-1", "shot-2"]
    assert entries[0]["start_sec"] == 0.0
    assert entries[1]["start_sec"] == 5.0
    assert entries[0]["duration_sec"] == 5.0
    licenses = json.loads(
        (ctx.output / "broll-licenses.json").read_text(encoding="utf-8")
    )
    assert licenses["assets"]["a1"]["license"] == "CC0"
    assert licenses["assets"]["a2"]["license"] == "CC-BY"


def test_match_without_shots_falls_back_to_the_whole_clip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "videoflow.steps.assets_match.list_assets",
        lambda limit=2000: [
            {
                "id": "a1",
                "name": "city sunrise",
                "kind": "video",
                "path": "/a1.mp4",
                "tags": [],
                "license": "CC0",
            }
        ],
    )
    ctx = context(tmp_path)
    ctx.metadata = {}

    AssetMatchStep().run(ctx, MatchParams(max_per_short=1, min_score=0.0), StepIO(stage="broll"))

    [entry] = ctx.metadata["broll_plan"]["Rotina produtiva"]
    assert entry["shot_id"] == ""
    assert entry["start_sec"] == 0.0
    assert entry["duration_sec"] == 5.0


def test_master_plan_accepts_approved_broll_assets_at_zero_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps.broll_master import BrollMasterParams, BrollMasterStep

    monkeypatch.setattr(
        "videoflow.steps.broll_master.list_assets",
        lambda limit=2000: [
            {
                "id": "b1",
                "name": "city sunrise",
                "kind": "broll",
                "path": "/b1.mp4",
                "tags": [],
                "license": "CC0",
            }
        ],
    )
    ctx = context(tmp_path)
    ctx.metadata["narrative_beats"] = [
        {
            "context_block_id": "block_001",
            "start_sec": 0.0,
            "end_sec": 5.0,
            "text": "cidade ao amanhecer",
            "extracted_entities": {},
        }
    ]

    BrollMasterStep().run(
        ctx,
        BrollMasterParams(min_score=0.0, max_per_block=1),
        StepIO(stage="broll.plan_master"),
    )

    entries = ctx.metadata["broll_plan"]["block_001"]
    assert len(entries) == 1
    assert entries[0]["path"] == "/b1.mp4"
    assert entries[0]["license"] == "CC0"
