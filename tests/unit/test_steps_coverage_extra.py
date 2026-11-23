"""Extra behavioral coverage for the content, delivery, flow, b-roll, score and
transcription steps. Everything runs through the public ``run`` methods with
local fakes for FFmpeg, ASR and LLM clients only.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.application.shorts import ShortClip
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ExportError, IngestError, TranscriptionError
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    Sentence,
    VideoSegment,
)
from videoflow.steps.base import EmptyParams, StepIO

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def make_media(base: Path, **overrides: object) -> MediaInfo:
    values: dict[str, object] = {
        "source_path": str(base / "source.mp4"),
        "duration_frames": 120,
        "fps_num": 30,
        "fps_den": 1,
        "width": 640,
        "height": 360,
        "audio_sample_rate": 48000,
    }
    values.update(overrides)
    return MediaInfo(**values)  # type: ignore[arg-type]


def sentence(
    index: int,
    start: int = 0,
    end: int = 1000,
    text: str = "hello",
    speaker: int = 0,
) -> Sentence:
    return Sentence(
        id=index,
        start_sample=start,
        end_sample=end,
        text=text,
        speaker=speaker,
    )


def make_state(base: Path, *, fps_num: int = 30) -> ProjectState:
    info = make_media(base, fps_num=fps_num)
    return ProjectState(
        media_info=info,
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_in_frame=0,
                source_out_frame=60,
                timeline_in_frame=0,
                timeline_out_frame=60,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="a1",
                source_in_sample=0,
                source_out_sample=96000,
                timeline_in_sample=0,
                timeline_out_sample=96000,
            )
        ],
    )


def make_context(
    base: Path,
    *,
    media_info: MediaInfo | None = None,
    transcript: list[Sentence] | None = None,
    state: ProjectState | None = None,
    shorts: list[dict[str, object]] | None = None,
    selected_shorts: list[object] | None = None,
    metadata: dict[str, object] | None = None,
    artifacts: dict[str, str] | None = None,
) -> PipelineContext:
    output = base / "out"
    work = output / "work"
    exports = output / "exports"
    for directory in (output, work, exports):
        directory.mkdir(parents=True, exist_ok=True)
    source = base / "source.mp4"
    source.write_bytes(b"fixture")
    return PipelineContext(
        source=source,
        output=output,
        work=work,
        exports=exports,
        media=media_info,
        transcript=list(transcript or []),
        state=state,
        shorts=list(shorts or []),
        selected_shorts=list(selected_shorts or []),
        metadata=dict(metadata or {}),
        artifacts=dict(artifacts or {}),
    )


def make_clip(title: str, *, start: int = 0, end: int = 48000) -> ShortClip:
    return ShortClip(
        title=title,
        start_sample=start,
        end_sample=end,
        sentence_ids=(0,),
        pieces=((start, end),),
        score_breakdown=(("hook_strength", 3.0), ("completeness", 1.0)),
    )


class _FakeFFmpeg:
    loudness: dict[str, float] = {"integrated_lufs": -16.0, "true_peak_dbfs": -2.0}
    thumbnails: list[tuple[Path, float]] = []
    mastered: list[tuple[Path, tuple[str, ...], int]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.log = kwargs.get("log")

    def master_audio(
        self,
        source: Path,
        destination: Path,
        *,
        filters: tuple[str, ...] = (),
        sample_rate: int = 48000,
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"wav")
        type(self).mastered.append((destination, tuple(filters), sample_rate))
        return destination

    def measure_loudness(self, source: Path) -> dict[str, float]:
        return dict(type(self).loudness)

    def render_thumbnail(
        self,
        source: Path,
        destination: Path,
        *,
        time_sec: float = 0.0,
        **kwargs: object,
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"png")
        type(self).thumbnails.append((destination, time_sec))
        return destination


# ---------------------------------------------------------------------------
# content.py
# ---------------------------------------------------------------------------


def test_bypass_step_reports_and_storyboard_paths(tmp_path: Path) -> None:
    from videoflow.steps.content import IdeaStep, StoryboardStep

    reports: list[tuple[int, str]] = []
    io = StepIO(progress=lambda stage, pct, msg: reports.append((pct, msg)))
    context = make_context(tmp_path)
    IdeaStep().run(context, EmptyParams(), io)
    assert reports[-1] == (100, "Bypassed")
    assert IdeaStep().run(context, EmptyParams(), StepIO()) is None

    with pytest.raises(IngestError, match="validated timeline"):
        StoryboardStep().run(context, EmptyParams(), StepIO())

    context.state = make_state(tmp_path)
    context.media = make_media(tmp_path)
    StoryboardStep().run(context, EmptyParams(), StepIO())
    payload = json.loads((context.output / "storyboard.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert [scene["id"] for scene in payload["scenes"]] == ["v1"]

    cached = StoryboardStep().cache_outputs(context)
    assert cached == (context.output / "storyboard.json",)
    context.artifacts.pop("storyboard")
    assert StoryboardStep().cache_outputs(context) == ()


def test_asset_index_skips_without_directory_and_indexes_files(tmp_path: Path) -> None:
    from videoflow.steps.content import AssetIndexParams, AssetIndexStep

    reports: list[str] = []
    io = StepIO(progress=lambda stage, pct, msg: reports.append(msg))
    context = make_context(tmp_path)
    AssetIndexStep().run(context, AssetIndexParams(), io)
    assert "Asset indexing skipped" in reports
    assert "assets_index" not in context.artifacts
    assert AssetIndexStep().cache_outputs(context) == ()

    library = tmp_path / "library"
    library.mkdir()
    (library / "clip.mp4").write_bytes(b"x")
    (library / "photo.png").write_bytes(b"x")
    (library / "notes.txt").write_text("ignore", encoding="utf-8")

    AssetIndexStep().run(context, AssetIndexParams(asset_dir=str(library), tags=["doc"]), io)
    payload = json.loads((context.output / "assets-index.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert len(payload["assets"]) == 2
    assert len(context.metadata["assets_index"]) == 2
    assert AssetIndexStep().cache_outputs(context) == (context.output / "assets-index.json",)


def test_audio_master_and_qa_measure_and_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps import content_audio
    from videoflow.steps.content import (
        AudioMasterParams,
        AudioMasterStep,
        AudioQaParams,
        AudioQaStep,
    )

    monkeypatch.setattr(content_audio, "FFmpegAdapter", _FakeFFmpeg)
    context = make_context(tmp_path)
    with pytest.raises(IngestError, match="ingested media"):
        AudioMasterStep().run(context, AudioMasterParams(), StepIO())

    context.media = make_media(tmp_path)
    AudioMasterStep().run(
        context,
        AudioMasterParams(highpass_hz=90, denoise=False, loudnorm=True),
        StepIO(),
    )
    target = context.output / "audio" / "master.wav"
    assert target.read_bytes() == b"wav"
    assert context.artifacts["audio_master"] == str(target)
    filters = json.loads(
        (context.output / "audio" / "master-filters.json").read_text(encoding="utf-8")
    )
    assert filters["filters"]
    assert context.metadata["audio_master_filters"] == filters["filters"]
    assert AudioMasterStep().cache_outputs(context) == (target,)

    monkeypatch.setattr(
        _FakeFFmpeg,
        "loudness",
        {"integrated_lufs": -16.0, "true_peak_dbfs": -2.0},
    )
    AudioQaStep().run(context, AudioQaParams(), StepIO())
    qa = json.loads((context.output / "audio" / "qa.json").read_text(encoding="utf-8"))
    assert qa["passed"] is True
    assert context.metadata["audio_qa"]["passed"] is True
    assert context.warnings == []
    assert AudioQaStep().cache_outputs(context) == (context.output / "audio" / "qa.json",)

    monkeypatch.setattr(
        _FakeFFmpeg,
        "loudness",
        {"integrated_lufs": -24.0, "true_peak_dbfs": 0.5},
    )
    with pytest.raises(ExportError, match="out of spec"):
        AudioQaStep().run(context, AudioQaParams(), StepIO())

    quality = SimpleNamespace(target_lufs=-14.0, true_peak_db=-2.0)
    monkeypatch.setattr(
        "videoflow.application.settings.load_settings",
        lambda: SimpleNamespace(quality=quality),
    )
    monkeypatch.setattr(
        _FakeFFmpeg,
        "loudness",
        {"integrated_lufs": -14.0, "true_peak_dbfs": -2.0},
    )
    AudioQaStep().run(
        context,
        AudioQaParams(target_lufs=-14.0, max_true_peak_db=-2.0),
        StepIO(),
    )
    qa = json.loads((context.output / "audio" / "qa.json").read_text(encoding="utf-8"))
    assert qa["target_lufs"] == -14.0
    assert qa["max_true_peak_db"] == -2.0

    def broken_settings() -> object:
        raise RuntimeError("settings exploded")

    monkeypatch.setattr("videoflow.application.settings.load_settings", broken_settings)
    monkeypatch.setattr(
        _FakeFFmpeg,
        "loudness",
        {"integrated_lufs": -15.5, "true_peak_dbfs": -2.0},
    )
    AudioQaStep().run(context, AudioQaParams(), StepIO())
    assert context.artifacts["audio_qa"].endswith("qa.json")


def test_color_grade_lut_validation_and_eq_filters(tmp_path: Path) -> None:
    from videoflow.steps.content import ColorGradeParams, ColorGradeStep

    context = make_context(tmp_path)
    with pytest.raises(IngestError, match="LUT does not exist"):
        ColorGradeStep().run(
            context, ColorGradeParams(lut_path=str(tmp_path / "missing.cube")), StepIO()
        )

    ColorGradeStep().run(context, ColorGradeParams(), StepIO())
    filters = json.loads((context.output / "color" / "filters.json").read_text(encoding="utf-8"))
    assert filters == {"filters": [], "lut": ""}
    assert ColorGradeStep().cache_outputs(context) == (context.output / "color" / "filters.json",)

    lut = tmp_path / "look.cube"
    lut.write_text("LUT", encoding="utf-8")
    ColorGradeStep().run(
        context,
        ColorGradeParams(lut_path=str(lut), brightness=0.1, contrast=1.2, gamma=1.1),
        StepIO(),
    )
    filters = json.loads((context.output / "color" / "filters.json").read_text(encoding="utf-8"))
    assert filters["filters"][0].startswith("lut3d=")
    assert "eq=brightness=0.1:contrast=1.2" in filters["filters"][1]
    assert filters["lut"] == str(lut)
    assert context.metadata["color_filters"] == filters["filters"]


def test_titles_lower_third_dedup_limit_and_cards(tmp_path: Path) -> None:
    from videoflow.steps.content import TitlesParams, TitlesStep

    context = make_context(tmp_path)
    with pytest.raises(IngestError, match="validated timeline"):
        TitlesStep().run(context, TitlesParams(), StepIO())

    state = make_state(tmp_path)
    state.transcript = [
        sentence(0, 0, 48000, "first", speaker=0),
        sentence(1, 48000, 96000, "same speaker", speaker=0),
        sentence(2, 96000, 144000, "second", speaker=1),
        sentence(3, 144000, 192000, "third", speaker=2),
    ]
    context.state = state
    context.media = None
    context.shorts = [{"title": "Short A"}, {}]
    TitlesStep().run(context, TitlesParams(max_lower_thirds=2), StepIO())

    payload = json.loads((context.output / "titles.json").read_text(encoding="utf-8"))
    assert [item["speaker"] for item in payload["lower_thirds"]] == [0, 1]
    assert payload["lower_thirds"][1]["start_sec"] == 2.0
    assert [card["kind"] for card in payload["title_cards"]] == ["short", "short"]
    assert payload["title_cards"][1]["text"] == "Short 2"
    assert (context.output / "titles.ass").is_file()
    assert context.metadata["titles"] == payload
    assert TitlesStep().cache_outputs(context) == (context.output / "titles.json",)

    state.transcript = [
        sentence(0, 0, 48000, "plain a", speaker=0),
        sentence(1, 48000, 96000, "plain b", speaker=1),
    ]
    TitlesStep().run(
        context,
        TitlesParams(max_lower_thirds=5, intro_title="Intro", outro_title="Outro"),
        StepIO(),
    )
    payload = json.loads((context.output / "titles.json").read_text(encoding="utf-8"))
    assert len(payload["lower_thirds"]) == 2
    assert [card["kind"] for card in payload["title_cards"]] == [
        "intro",
        "short",
        "short",
        "outro",
    ]
    assert payload["title_cards"][-1]["start_sec"] == 0.0


def test_thumbnail_variants_use_adapter_and_cache_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps import content_visual
    from videoflow.steps.content import ThumbnailParams, ThumbnailStep

    monkeypatch.setattr(content_visual, "FFmpegAdapter", _FakeFFmpeg)
    context = make_context(tmp_path)
    with pytest.raises(IngestError, match="ingested media"):
        ThumbnailStep().run(context, ThumbnailParams(), StepIO())

    _FakeFFmpeg.thumbnails.clear()
    context.media = make_media(tmp_path)
    ThumbnailStep().run(context, ThumbnailParams(variants=3, title="Cover"), StepIO())
    assert len(_FakeFFmpeg.thumbnails) == 3
    assert context.artifacts["thumbnail"] == str(context.output / "thumbnails" / "thumbnail-1.png")
    assert len(context.metadata["thumbnails"]) == 3
    assert context.metadata["thumbnail_title"] == "Cover"
    assert len(ThumbnailStep().cache_outputs(context)) == 3
    context.metadata.pop("thumbnails")
    assert ThumbnailStep().cache_outputs(context) == ()

    ThumbnailStep().run(context, ThumbnailParams(), StepIO())
    assert len(context.metadata["thumbnails"]) == 1


def test_analytics_import_numeric_averages_and_errors(tmp_path: Path) -> None:
    from videoflow.steps.content import AnalyticsParams, AnalyticsStep

    context = make_context(tmp_path)
    with pytest.raises(IngestError, match="does not exist"):
        AnalyticsStep().run(
            context, AnalyticsParams(csv_path=str(tmp_path / "missing.csv")), StepIO()
        )

    AnalyticsStep().run(context, AnalyticsParams(), StepIO())
    payload = json.loads((context.output / "analytics.json").read_text(encoding="utf-8"))
    assert payload["row_count"] == 0
    assert payload["columns"] == []
    assert AnalyticsStep().cache_outputs(context) == (context.output / "analytics.json",)

    csv_path = tmp_path / "metrics.csv"
    csv_path.write_text(
        "title,duration_sec,retention\na,10,0.5\nb,20,0.7\n",
        encoding="utf-8",
    )
    AnalyticsStep().run(context, AnalyticsParams(csv_path=str(csv_path)), StepIO())
    payload = json.loads((context.output / "analytics.json").read_text(encoding="utf-8"))
    assert payload["row_count"] == 2
    assert payload["columns"] == ["duration_sec", "retention", "title"]
    assert payload["averages"] == {"duration_sec": 15.0, "retention": 0.6}
    assert context.metadata["analytics"]["row_count"] == 2


def test_review_step_reports_missing_and_ready_checks(tmp_path: Path) -> None:
    from videoflow.steps.content import ReviewStep

    context = make_context(tmp_path)
    reports: list[str] = []
    io = StepIO(progress=lambda stage, pct, msg: reports.append(msg))
    ReviewStep().run(context, EmptyParams(), io)
    payload = json.loads((context.output / "review.json").read_text(encoding="utf-8"))
    assert payload["approved"] is False
    assert payload["pending"] == [
        "timeline",
        "captions",
        "shorts",
        "thumbnail",
        "audio_master",
        "titles",
    ]
    assert context.metadata["review"] == payload
    assert ReviewStep().cache_outputs(context) == (context.output / "review.json",)
    assert "0/6 checks ready" in reports[-1]

    context.state = make_state(tmp_path)
    context.transcript = [sentence(0)]
    context.shorts = [{"title": "one"}]
    for name in ("thumbnail", "audio_master", "titles"):
        context.artifacts[name] = f"{name}.json"
    ReviewStep().run(context, EmptyParams(), io)
    payload = json.loads((context.output / "review.json").read_text(encoding="utf-8"))
    assert payload["pending"] == []
    assert "6/6 checks ready" in reports[-1]


# ---------------------------------------------------------------------------
# delivery.py
# ---------------------------------------------------------------------------


def test_metadata_pack_collects_and_records_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps import delivery_metadata
    from videoflow.steps.delivery import MetadataPackParams, MetadataPackStep

    def fake_metadata(**kwargs: object) -> dict[str, object]:
        index = int(kwargs["index"])  # type: ignore[arg-type]
        if index == 1:
            raise RuntimeError("metadata exploded")
        return {
            "title": f"short-{index}",
            "platform": kwargs["platform"],
            "hashtags": list(kwargs["extra_hashtags"]),  # type: ignore[arg-type]
        }

    monkeypatch.setattr(delivery_metadata, "generate_short_metadata", fake_metadata)
    context = make_context(
        tmp_path,
        shorts=[{"title": "one"}, {"title": "two"}],
    )
    reports: list[str] = []
    MetadataPackStep().run(
        context,
        MetadataPackParams(platform="tiktok", hashtags=["#fyp"]),
        StepIO(progress=lambda stage, pct, msg: reports.append(msg)),
    )
    entries = json.loads(
        (context.output / "delivery" / "metadata.json").read_text(encoding="utf-8")
    )
    assert [entry["title"] for entry in entries] == ["short-0"]
    assert entries[0]["hashtags"] == ["#fyp"]
    assert context.warnings and "Metadata failed for Short 1" in context.warnings[0]
    assert "1 metadata record(s)" in reports[-1]


def test_thumbnail_pack_copies_variants_and_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps import delivery_metadata
    from videoflow.steps.delivery import ThumbnailPackParams, ThumbnailPackStep

    def fake_thumbnail(**kwargs: object) -> dict[str, object]:
        index = int(kwargs["index"])  # type: ignore[arg-type]
        if index == 1:
            raise RuntimeError("thumbnail exploded")
        output = Path(str(kwargs["output"]))
        target = output / "shorts" / "thumbs" / f"thumb-{index}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"png")
        return {"path": str(target)}

    monkeypatch.setattr(delivery_metadata, "generate_short_thumbnail", fake_thumbnail)
    context = make_context(
        tmp_path,
        shorts=[
            {"title": "one", "duration_sec": 10.0},
            {"title": "two", "duration_sec": 8.0},
        ],
    )
    ThumbnailPackStep().run(context, ThumbnailPackParams(variants=2), StepIO())
    listing = context.metadata["thumbnail_pack"]
    assert listing["variants"] == ["variant-1-1.png", "variant-1-2.png"]
    assert context.warnings and "Thumbnail failed for Short 1" in context.warnings[0]
    assert (context.output / "thumbnails" / "variant-1-1.png").is_file()


def test_analytics_review_median_and_unreadable_source(tmp_path: Path) -> None:
    from videoflow.steps.delivery import AnalyticsReviewParams, AnalyticsReviewStep

    context = make_context(tmp_path)
    AnalyticsReviewStep().run(context, AnalyticsReviewParams(), StepIO())
    review = json.loads(
        (context.output / "delivery" / "analytics-review.json").read_text(encoding="utf-8")
    )
    assert review == {
        "sample_size": 0,
        "suggested_duration_sec": 0.0,
        "weights": {"hook_strength": 1.0, "payoff": 1.0, "duration_fit": 1.0},
    }
    assert context.metadata["analytics_weights"] == review["weights"]

    analytics = context.output / "analytics.json"
    analytics.write_text(
        json.dumps(
            {
                "rows": [
                    {"duration_sec": "10", "ctr": "0.1"},
                    {"duration_sec": "30", "ctr": "0.2"},
                    {"duration_sec": "bad", "ctr": "n/a"},
                ]
            }
        ),
        encoding="utf-8",
    )
    context.artifacts["analytics"] = str(analytics)
    AnalyticsReviewStep().run(context, AnalyticsReviewParams(), StepIO())
    review = json.loads(
        (context.output / "delivery" / "analytics-review.json").read_text(encoding="utf-8")
    )
    assert review["sample_size"] == 3
    assert review["suggested_duration_sec"] == 30.0
    assert review["weights"]["duration_fit"] == 1.5

    analytics.write_text("{ not json", encoding="utf-8")
    AnalyticsReviewStep().run(context, AnalyticsReviewParams(), StepIO())
    review = json.loads(
        (context.output / "delivery" / "analytics-review.json").read_text(encoding="utf-8")
    )
    assert review["sample_size"] == 0

    analytics.write_text(
        json.dumps({"rows": [{"duration_sec": "bad"}, {"duration_sec": ""}]}),
        encoding="utf-8",
    )
    AnalyticsReviewStep().run(context, AnalyticsReviewParams(), StepIO())
    review = json.loads(
        (context.output / "delivery" / "analytics-review.json").read_text(encoding="utf-8")
    )
    assert review["sample_size"] == 2
    assert review["suggested_duration_sec"] == 0.0
    assert review["weights"]["duration_fit"] == 1.0


def test_experiment_without_metrics_and_selection_failure(tmp_path: Path) -> None:
    from videoflow.steps.delivery import ExperimentEvaluateStep, ExperimentParams

    reports: list[str] = []
    io = StepIO(progress=lambda stage, pct, msg: reports.append(msg))
    context = make_context(tmp_path)
    ExperimentEvaluateStep().run(context, ExperimentParams(), io)
    payload = json.loads(
        (context.output / "delivery" / "experiment.json").read_text(encoding="utf-8")
    )
    assert payload == {"metrics": [], "winner": None}
    assert "No metrics yet" in reports[-1]

    (context.output / "thumbnail_metrics.json").write_text(
        json.dumps({"ghost.png": {"impressions": 10, "clicks": 4}}),
        encoding="utf-8",
    )
    ExperimentEvaluateStep().run(context, ExperimentParams(), io)
    payload = json.loads(
        (context.output / "delivery" / "experiment.json").read_text(encoding="utf-8")
    )
    assert payload["winner"]["name"] == "ghost.png"
    assert any("winner selection failed" in warning for warning in context.warnings)
    assert "Experiment evaluated" in reports[-1]


def test_chapters_from_transcript_or_state(tmp_path: Path) -> None:
    from videoflow.steps.delivery import ChaptersParams, ChaptersStep

    context = make_context(
        tmp_path,
        media_info=make_media(tmp_path, audio_sample_rate=1000),
        transcript=[
            sentence(0, 0, 1000, "alpha"),
            sentence(1, 1000, 2000, "beta"),
            sentence(2, 2000, 3000, "gamma"),
            sentence(3, 3000, 4000, "delta"),
        ],
    )
    ChaptersStep().run(context, ChaptersParams(max_chapters=2), StepIO())
    payload = json.loads((context.output / "chapters.json").read_text(encoding="utf-8"))
    assert [chapter["title"] for chapter in payload["chapters"]] == ["alpha", "gamma"]
    assert payload["chapters"][1]["start_sec"] == 2.0
    assert context.artifacts["chapters"].endswith("chapters.json")

    state = make_state(tmp_path)
    state.transcript = [sentence(0, 0, 500, "from state")]
    fallback = make_context(
        tmp_path / "fallback",
        media_info=make_media(tmp_path / "fallback", audio_sample_rate=500),
        state=state,
    )
    ChaptersStep().run(fallback, ChaptersParams(), StepIO())
    payload = json.loads((fallback.output / "chapters.json").read_text(encoding="utf-8"))
    assert payload["chapters"][0]["title"] == "from state"


def test_nle_qa_writes_a_report(tmp_path: Path) -> None:
    from videoflow.steps.delivery import NleQaParams, NleQaStep

    context = make_context(tmp_path)
    NleQaStep().run(context, NleQaParams(), StepIO())
    report = json.loads((context.output / "exports" / "qa-report.json").read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert set(report["exports"]) == {"fcpxml", "xmeml", "kdenlive"}
    assert context.artifacts["nle_qa"].endswith("qa-report.json")


def test_delivery_package_edges_without_winner_or_music(tmp_path: Path) -> None:
    from videoflow.steps.delivery import DeliveryPackageStep, PackageParams

    context = make_context(
        tmp_path,
        shorts=[
            {"title": "kept"},
        ],
        metadata={
            "sfx_plan": {
                "one": [
                    "not a cue",
                    {"no_path": True},
                    {"path": "/sfx/whoosh.wav"},
                    {"path": "/sfx/whoosh.wav"},
                ]
            }
        },
    )
    context.shorts.append("not a mapping")  # type: ignore[arg-type]
    (context.output / "thumbnail_choice.json").write_text(
        json.dumps({"selected": "ghost.png"}), encoding="utf-8"
    )
    DeliveryPackageStep().run(context, PackageParams(), StepIO())
    manifest = json.loads(
        (context.output / "delivery" / "package.json").read_text(encoding="utf-8")
    )
    assert manifest["thumbnail"] == ""
    assert not (context.output / "delivery" / "thumbnail.png").exists()
    assert manifest["shorts"] == [{"index": 0, "title": "kept", "path": "", "thumbnail": ""}]
    assert manifest["music"] == []
    assert manifest["sfx"] == ["/sfx/whoosh.wav"]
    assert context.metadata["delivery_package"] == manifest

    (context.output / "thumbnail_choice.json").unlink()
    DeliveryPackageStep().run(context, PackageParams(), StepIO())
    manifest = json.loads(
        (context.output / "delivery" / "package.json").read_text(encoding="utf-8")
    )
    assert manifest["thumbnail"] == ""

    thumbs = context.output / "thumbnails"
    thumbs.mkdir()
    (thumbs / "variant-9.png").write_bytes(b"png")
    (context.output / "thumbnail_choice.json").write_text(
        json.dumps({"selected": "variant-9.png"}), encoding="utf-8"
    )
    music = tmp_path / "music"
    music.mkdir()
    (music / "theme.mp3").write_bytes(b"music")
    DeliveryPackageStep().run(context, PackageParams(), StepIO())
    manifest = json.loads(
        (context.output / "delivery" / "package.json").read_text(encoding="utf-8")
    )
    assert manifest["thumbnail"] == str(context.output / "delivery" / "thumbnail.png")
    assert manifest["music"] == [str(music / "theme.mp3")]
    assert manifest["thumbnail_variants"] == ["variant-9.png"]

    context.metadata["sfx_plan"] = ["not", "a", "dict"]
    DeliveryPackageStep().run(
        context,
        PackageParams(include_music=False, copy_thumbnail=False),
        StepIO(),
    )
    manifest = json.loads(
        (context.output / "delivery" / "package.json").read_text(encoding="utf-8")
    )
    assert manifest["music"] == []
    assert manifest["sfx"] == []

    DeliveryPackageStep().run(
        context,
        PackageParams(
            include_music=False,
            include_sfx=False,
            copy_thumbnail=False,
        ),
        StepIO(),
    )
    manifest = json.loads(
        (context.output / "delivery" / "package.json").read_text(encoding="utf-8")
    )
    assert manifest["sfx"] == []


# ---------------------------------------------------------------------------
# flow.py
# ---------------------------------------------------------------------------


def test_condition_helpers_cover_every_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps.flow import FlowParams, _condition_holds

    context = make_context(tmp_path)
    assert _condition_holds(FlowParams(condition="always"), context) is True
    assert _condition_holds(FlowParams(condition="no"), context) is False
    assert _condition_holds(FlowParams(condition="has_shorts"), context) is False
    assert _condition_holds(FlowParams(condition="has_transcript"), context) is False

    context.selected_shorts = [make_clip("x")]
    context.transcript = [sentence(0)]
    context.artifacts["timeline"] = "t.json"
    context.metadata["scenes"] = [{"id": 1}]
    target = tmp_path / "present.txt"
    target.write_text("x", encoding="utf-8")
    assert _condition_holds(FlowParams(condition="shorts"), context) is True
    assert _condition_holds(FlowParams(condition="transcript"), context) is True
    assert _condition_holds(FlowParams(condition="artifact:timeline"), context) is True
    assert _condition_holds(FlowParams(condition="metadata:scenes"), context) is True
    assert _condition_holds(FlowParams(condition=f"file:{target}"), context) is True

    with pytest.raises(ValueError, match="Unknown flow condition"):
        _condition_holds(FlowParams(condition="bogus"), context)


def test_flow_collection_sources(tmp_path: Path) -> None:
    from videoflow.steps.flow import FlowParams, _collection

    context = make_context(tmp_path)
    (tmp_path / "a.mp4").write_bytes(b"a")
    (tmp_path / "b.mp4").write_bytes(b"b")
    (context.output / "nested.mp4").write_bytes(b"c")

    context.selected_shorts = [make_clip("x")]
    assert len(_collection(context, FlowParams(over="shorts"))) == 1
    context.transcript = [sentence(0)]
    assert len(_collection(context, FlowParams(over="sentences"))) == 1
    assert len(_collection(context, FlowParams(over="files", glob="**/*.mp4", max_items=10))) == 2
    assert len(_collection(context, FlowParams(over="files", glob="*.mp4", max_items=1))) == 1
    assert _collection(context, FlowParams(over="scenes")) == []
    context.state = make_state(tmp_path)
    assert len(_collection(context, FlowParams(over="scenes"))) == 1
    context.metadata["scenes"] = [{"id": "scene"}]
    assert _collection(context, FlowParams(over="scenes")) == [{"id": "scene"}]
    context.metadata["assets_index"] = [{"id": "asset"}]
    assert _collection(context, FlowParams(over="assets")) == [{"id": "asset"}]
    context.metadata["assets_index"] = "broken"
    assert _collection(context, FlowParams(over="assets")) == []
    assert _collection(context, FlowParams(over="none")) == []


def test_conditional_branches_and_nested_flow(tmp_path: Path) -> None:
    from videoflow.steps.flow import (
        ConditionalStep,
        FlowParams,
        FlowStepSpec,
        _FlowStep,
        _run_steps,
    )

    context = make_context(tmp_path)
    reports: list[str] = []
    io = StepIO(progress=lambda stage, pct, msg: reports.append(msg))

    with pytest.raises(NotImplementedError):
        _FlowStep().run(context, EmptyParams(), io)
    with pytest.raises(ValueError, match="too deep"):
        _run_steps(context, [], io, depth=7)

    ConditionalStep().run(context, FlowParams(condition="false"), io)
    assert context.metadata["flow_last_condition"] is False
    assert any("nothing to run" in message for message in reports)

    specs = [
        FlowStepSpec(type="content.idea"),
        FlowStepSpec(type="flow.conditional", params={"condition": "always"}),
    ]
    ConditionalStep().run(
        context,
        FlowParams(condition="always", when_true=specs),
        io,
    )
    assert context.metadata["flow_last_condition"] is True

    ConditionalStep().run(
        context,
        FlowParams(
            condition="true",
            steps=[FlowStepSpec(type="content.idea")],
        ),
        io,
    )
    assert "finished" in reports[-1]


def test_subflow_runs_inline_and_recipe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from videoflow.steps import flow
    from videoflow.steps.flow import FlowParams, FlowStepSpec, SubflowStep

    context = make_context(tmp_path)
    SubflowStep().run(context, FlowParams(), StepIO())
    assert context.metadata == {}

    recipe = SimpleNamespace(steps=[SimpleNamespace(type="content.idea", params={})])
    monkeypatch.setattr(flow, "_recipe_steps", flow._recipe_steps)
    import videoflow.engine.recipes as recipes

    monkeypatch.setattr(recipes, "get_recipe", lambda recipe_id: recipe)
    SubflowStep().run(context, FlowParams(recipe_id="demo"), StepIO())

    SubflowStep().run(
        context,
        FlowParams(steps=[FlowStepSpec(type="content.idea")]),
        StepIO(),
    )


def test_loop_over_shorts_files_and_empty_collections(tmp_path: Path) -> None:
    from videoflow.steps.flow import FlowParams, FlowStepSpec, LoopStep

    reports: list[str] = []
    io = StepIO(progress=lambda stage, pct, msg: reports.append(msg))
    context = make_context(tmp_path)
    LoopStep().run(
        context,
        FlowParams(over="shorts", steps=[FlowStepSpec(type="content.idea")]),
        io,
    )
    assert "no items" in reports[-1]
    assert "loop_item" not in context.metadata

    context.selected_shorts = [{"title": "a"}, {"title": "b"}]
    LoopStep().run(
        context,
        FlowParams(over="shorts", steps=[FlowStepSpec(type="content.idea")]),
        io,
    )
    assert "Loop finished (2 item(s))" in reports[-1]
    assert "loop_item" not in context.metadata

    LoopStep().run(context, FlowParams(over="sentences"), io)
    assert "no items" in reports[-1]

    isolated = make_context(tmp_path / "isolated")
    (tmp_path / "isolated" / "a.mp4").write_bytes(b"a")
    (tmp_path / "isolated" / "b.mp4").write_bytes(b"b")
    (isolated.output / "nested.mp4").write_bytes(b"c")
    library = tmp_path / "library"
    library.mkdir()
    (library / "clip.mp4").write_bytes(b"x")
    LoopStep().run(
        isolated,
        FlowParams(
            over="files",
            glob="**/*.mp4",
            max_items=10,
            steps=[FlowStepSpec(type="assets.index", params={"asset_dir": str(library)})],
        ),
        io,
    )
    runs = isolated.metadata["loop_runs"]
    assert len(runs) == 2
    assert all(Path(run["output"]).is_dir() for run in runs)
    assert any(key.endswith("assets_index") for key in isolated.artifacts)
    assert isolated.warnings == []

    limited = make_context(tmp_path / "limited")
    (tmp_path / "limited" / "a.mp4").write_bytes(b"a")
    (tmp_path / "limited" / "b.mp4").write_bytes(b"b")
    LoopStep().run(
        limited,
        FlowParams(over="files", glob="*.mp4", max_items=1),
        io,
    )
    assert len(limited.metadata["loop_runs"]) == 1


def test_map_no_items_and_sequential_error_modes(tmp_path: Path) -> None:
    from videoflow.steps.flow import FlowParams, FlowStepSpec, MapStep

    context = make_context(tmp_path)
    for over in ("none", "sentences", "scenes", "assets", "shorts"):
        collect = f"empty_{over}"
        MapStep().run(context, FlowParams(over=over, collect=collect), StepIO())
        assert context.metadata[collect] == []

    context.metadata["scenes"] = [{"id": "scene"}]
    MapStep().run(
        context,
        FlowParams(
            over="scenes",
            collect="scenes_out",
            steps=[FlowStepSpec(type="content.idea")],
        ),
        StepIO(),
    )
    assert len(context.metadata["scenes_out"]) == 1
    assert context.metadata["scenes_out"][0]["ok"] is True

    context.transcript = [sentence(0, 0, 1000, "alpha")]
    MapStep().run(
        context,
        FlowParams(
            over="sentences",
            collect="skipped",
            on_error="skip",
            steps=[FlowStepSpec(type="transcribe")],
        ),
        StepIO(),
    )
    assert context.metadata["skipped"][0]["ok"] is False
    assert any("Map item 1 failed" in warning for warning in context.warnings)

    MapStep().run(
        context,
        FlowParams(
            over="sentences",
            collect="continued",
            on_error="continue",
            steps=[FlowStepSpec(type="transcribe")],
        ),
        StepIO(),
    )
    assert context.metadata["continued"][0]["ok"] is False

    with pytest.raises(IngestError):
        MapStep().run(
            context,
            FlowParams(
                over="sentences",
                collect="failed",
                on_error="fail",
                steps=[FlowStepSpec(type="transcribe")],
            ),
            StepIO(),
        )


def test_map_parallel_caps_workers_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps.flow import FlowParams, FlowStepSpec, MapStep

    monkeypatch.setenv("VIDEOWFLOW_PROVIDER_CONCURRENCY", "1")
    context = make_context(tmp_path)
    (tmp_path / "a.mp4").write_bytes(b"a")
    (tmp_path / "b.mp4").write_bytes(b"b")
    MapStep().run(
        context,
        FlowParams(
            over="files",
            glob="*.mp4",
            parallel=2,
            on_error="continue",
            steps=[FlowStepSpec(type="transcribe")],
        ),
        StepIO(),
    )
    assert any("capped at 1" in warning for warning in context.warnings)
    assert [result["ok"] for result in context.metadata["mapped"]] == [False, False]


def test_reduce_modes_and_missing_source(tmp_path: Path) -> None:
    from videoflow.steps.flow import FlowParams, ReduceStep

    context = make_context(tmp_path)
    context.metadata["mapped"] = [
        {"index": 1, "score": 5},
        {"index": 2, "score": 9},
        {"index": 3, "score": "bad"},
        "not a mapping",
    ]
    ReduceStep().run(context, FlowParams(source="mapped", mode="best_of"), StepIO())
    assert context.metadata["reduced"] == [{"index": 2, "score": 9}]

    ReduceStep().run(
        context,
        FlowParams(source="mapped", mode="top_k", top_k=2, collect="top"),
        StepIO(),
    )
    assert len(context.metadata["top"]) == 2

    ReduceStep().run(
        context,
        FlowParams(source="mapped", mode="all", collect="everything"),
        StepIO(),
    )
    assert len(context.metadata["everything"]) == 4

    ReduceStep().run(context, FlowParams(source="missing"), StepIO())
    assert context.metadata["reduced"] == []


def test_memory_workers_falls_back_when_proc_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from videoflow.steps.flow import _memory_workers

    assert _memory_workers() >= 1

    def broken_open(*args: object, **kwargs: object) -> object:
        raise OSError("no proc")

    monkeypatch.setattr("builtins.open", broken_open)
    assert _memory_workers() == 8

    import io as io_module

    monkeypatch.setattr(
        "builtins.open",
        lambda *args, **kwargs: io_module.StringIO("MemTotal: 1024 kB\n"),
    )
    assert _memory_workers() == 8


def test_flow_file_scanning_survives_relative_path_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps.flow import FlowParams, LoopStep, _collection

    context = make_context(tmp_path)
    (tmp_path / "a.mp4").write_bytes(b"a")

    def broken_relative(self: Path, other: object) -> bool:
        raise ValueError("different drive")

    monkeypatch.setattr(Path, "is_relative_to", broken_relative)
    items = _collection(context, FlowParams(over="files", glob="*.mp4"))
    assert items == [{"path": str(tmp_path / "a.mp4")}]

    looped = make_context(tmp_path / "looped")
    (tmp_path / "looped" / "b.mp4").write_bytes(b"b")
    LoopStep().run(
        looped,
        FlowParams(over="files", glob="*.mp4"),
        StepIO(),
    )
    assert len(looped.metadata["loop_runs"]) == 1


def test_map_parallel_success_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from videoflow.steps import flow
    from videoflow.steps.flow import FlowParams, FlowStepSpec, MapStep

    monkeypatch.setenv("VIDEOWFLOW_PROVIDER_CONCURRENCY", "8")
    monkeypatch.setattr(flow, "_memory_workers", lambda: 8)
    monkeypatch.setattr("os.cpu_count", lambda: 8)
    metrics = tmp_path / "metrics.csv"
    metrics.write_text("title,ctr\na,0.1\n", encoding="utf-8")
    context = make_context(
        tmp_path,
        metadata={"assets_index": [{"id": "a"}, {"id": "b"}]},
    )
    MapStep().run(
        context,
        FlowParams(
            over="assets",
            parallel=2,
            collect="parallel",
            steps=[FlowStepSpec(type="analytics.import", params={"csv_path": str(metrics)})],
        ),
        StepIO(),
    )
    results = context.metadata["parallel"]
    assert [item["ok"] for item in results] == [True, True]
    assert [item["index"] for item in results] == [1, 2]
    assert any(key.endswith("analytics") for key in context.artifacts)
    assert not any("capped" in warning for warning in context.warnings)


def test_map_parallel_failure_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from videoflow.steps.flow import FlowParams, FlowStepSpec, MapStep

    monkeypatch.setenv("VIDEOWFLOW_PROVIDER_CONCURRENCY", "2")
    context = make_context(
        tmp_path,
        metadata={"assets_index": [{"id": "a"}, {"id": "b"}]},
    )
    with pytest.raises(IngestError):
        MapStep().run(
            context,
            FlowParams(
                over="assets",
                parallel=2,
                steps=[FlowStepSpec(type="transcribe")],
            ),
            StepIO(),
        )


# ---------------------------------------------------------------------------
# broll.py
# ---------------------------------------------------------------------------


def test_broll_skips_without_shorts_or_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps.broll import BrollParams, BrollStep

    stock = SimpleNamespace(
        provider="pexels",
        asset_dir="/tmp/stock",
        pexels_key_env="VIDEOWFLOW_TEST_PEXELS",
    )
    monkeypatch.setattr(
        "videoflow.application.settings.load_settings",
        lambda: SimpleNamespace(stock=stock),
    )
    context = make_context(tmp_path)
    reports: list[str] = []
    BrollStep().run(
        context,
        BrollParams(),
        StepIO(progress=lambda stage, pct, msg: reports.append(msg)),
    )
    assert "No Shorts selected" in reports[-1]
    assert "broll_plan" not in context.metadata

    local_stock = SimpleNamespace(provider="local", asset_dir="", pexels_key_env="")
    monkeypatch.setattr(
        "videoflow.application.settings.load_settings",
        lambda: SimpleNamespace(stock=local_stock),
    )
    plain = make_context(tmp_path / "plain")
    BrollStep().run(plain, BrollParams(), StepIO())
    assert "broll_plan" not in plain.metadata

    empty = make_context(tmp_path / "empty")
    empty.selected_shorts = [make_clip("lonely")]

    def no_settings() -> object:
        raise RuntimeError("settings unavailable")

    monkeypatch.setattr("videoflow.application.settings.load_settings", no_settings)
    BrollStep().run(empty, BrollParams(provider="local"), StepIO())
    assert empty.metadata["broll_plan"] == {}
    assert any("no local asset directory" in warning for warning in empty.warnings)

    pexels = make_context(tmp_path / "pexels")
    pexels.selected_shorts = [make_clip("lonely")]
    monkeypatch.delenv("VIDEOWFLOW_UNSET_KEY", raising=False)
    BrollStep().run(
        pexels,
        BrollParams(provider="pexels", api_key_env="VIDEOWFLOW_UNSET_KEY"),
        StepIO(),
    )
    assert pexels.metadata["broll_plan"] == {}
    assert any("VIDEOWFLOW_UNSET_KEY is not set" in warning for warning in pexels.warnings)

    from videoflow.steps import broll as broll_module

    class FakeStock:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

        def search(self, query: str, *, limit: int) -> list[object]:
            return []

        def download(self, asset: object, destination: Path) -> Path:
            raise AssertionError("download should not be called")

    monkeypatch.setattr(broll_module, "PexelsBrollProvider", FakeStock)
    monkeypatch.setenv("VIDEOWFLOW_SET_KEY", "secret")
    configured = make_context(tmp_path / "configured")
    configured.selected_shorts = [make_clip("lonely")]
    BrollStep().run(
        configured,
        BrollParams(provider="pexels", api_key_env="VIDEOWFLOW_SET_KEY"),
        StepIO(),
    )
    assert configured.metadata["broll_plan"] == {"lonely": []}
    assert configured.artifacts["broll"].endswith("broll.json")


def test_broll_local_provider_plans_deduped_assets(tmp_path: Path) -> None:
    from videoflow.steps.broll import BrollParams, BrollStep

    library = tmp_path / "assets"
    library.mkdir()
    (library / "city-sunrise.mp4").write_bytes(b"x")
    (library / "city-night.mp4").write_bytes(b"x")
    (library / "office-desk.mp4").write_bytes(b"x")
    context = make_context(tmp_path)
    context.selected_shorts = [
        make_clip("city sunrise"),
        make_clip("office desk"),
    ]
    BrollStep().run(
        context,
        BrollParams(provider="local", asset_dir=str(library), max_per_short=1),
        StepIO(),
    )
    plan = context.metadata["broll_plan"]
    assert len(plan["city sunrise"]) == 1
    assert len(plan["office desk"]) == 1
    first = Path(plan["city sunrise"][0]["path"]).name
    second = Path(plan["office desk"][0]["path"]).name
    assert first != second
    assert plan["city sunrise"][0]["license"] == "operator"
    payload = json.loads((context.output / "broll.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert context.artifacts["broll"].endswith("broll.json")
    assert context.hashes["broll"]


def test_broll_downloads_urls_and_records_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.domains.media.broll_providers import BrollAsset
    from videoflow.steps.broll import BrollParams, BrollStep

    class FakeProvider:
        def search(self, query: str, *, limit: int) -> list[BrollAsset]:
            if "explode" in query:
                raise RuntimeError("search exploded")
            return [
                BrollAsset(
                    provider="pexels",
                    url="https://cdn.example/clip.mp4?token=1",
                    attribution="Creator",
                    license="Pexels License",
                ),
                BrollAsset(provider="pexels", url="https://cdn.example/broken.mov"),
                BrollAsset(provider="pexels"),
                BrollAsset(
                    provider="pexels",
                    url="https://cdn.example/clip.mp4?token=1",
                ),
            ]

        def download(self, asset: BrollAsset, destination: Path) -> Path:
            if "broken" in asset.url:
                raise RuntimeError("download exploded")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"video")
            return destination

    monkeypatch.setattr(BrollStep, "_provider", lambda self, options, context: FakeProvider())
    context = make_context(tmp_path)
    context.selected_shorts = [
        make_clip("clip"),
        make_clip("explode"),
    ]
    BrollStep().run(context, BrollParams(provider="pexels", max_per_short=5), StepIO())
    plan = context.metadata["broll_plan"]
    assert len(plan["clip"]) == 1
    downloaded = Path(plan["clip"][0]["path"])
    assert downloaded.is_file()
    assert downloaded.name.endswith(".mp4")
    assert plan["clip"][0]["attribution"] == "Creator"
    assert plan["clip"][0]["provider"] == "pexels"
    assert plan["explode"] == []
    assert any("search failed for explode" in warning for warning in context.warnings)
    assert any("download failed" in warning for warning in context.warnings)


# ---------------------------------------------------------------------------
# shorts_score.py
# ---------------------------------------------------------------------------


def test_score_without_shorts_returns_early(tmp_path: Path) -> None:
    from videoflow.steps.shorts_score import ScoreParams, ShortsScoreStep

    context = make_context(tmp_path)
    reports: list[str] = []
    ShortsScoreStep().run(
        context,
        ScoreParams(),
        StepIO(progress=lambda stage, pct, msg: reports.append(msg)),
    )
    assert "No Shorts to score" in reports[-1]
    assert "shorts_scores" not in context.artifacts


def test_score_reads_analytics_review_file_and_survives_corruption(
    tmp_path: Path,
) -> None:
    from videoflow.steps.shorts_score import ScoreParams, ShortsScoreStep

    context = make_context(
        tmp_path,
        selected_shorts=[make_clip("alpha one"), make_clip("beta two")],
    )
    review_dir = context.output / "delivery"
    review_dir.mkdir(parents=True, exist_ok=True)
    review = review_dir / "analytics-review.json"
    review.write_text(
        json.dumps({"weights": {"hook_strength": 2.0, "ignored": "nope"}}),
        encoding="utf-8",
    )
    ShortsScoreStep().run(context, ScoreParams(profile="tiktok"), StepIO())
    report = json.loads(
        (context.output / "shorts-selection-report.json").read_text(encoding="utf-8")
    )
    assert report["analytics_weights"] == {
        "hook_strength": 2.0,
        "ignored": "nope",
    }
    assert report["weights"]["hook_strength"] == 2.0
    assert report["weights"]["analytics"] == 1.0
    assert report["profile"] == "tiktok"
    assert context.shorts and len(context.shorts) == 2

    corrupt = make_context(
        tmp_path / "corrupt",
        selected_shorts=[make_clip("gamma three")],
    )
    directory = corrupt.output / "delivery"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "analytics-review.json").write_text("{ bad", encoding="utf-8")
    ShortsScoreStep().run(corrupt, ScoreParams(), StepIO())
    report = json.loads(
        (corrupt.output / "shorts-selection-report.json").read_text(encoding="utf-8")
    )
    assert report["analytics_weights"] == {}

    weighted = make_context(
        tmp_path / "weighted",
        selected_shorts=[make_clip("delta four")],
        metadata={"analytics_weights": {"completeness": 4.0}},
    )
    ShortsScoreStep().run(weighted, ScoreParams(), StepIO())
    report = json.loads(
        (weighted.output / "shorts-selection-report.json").read_text(encoding="utf-8")
    )
    assert report["analytics_weights"] == {"completeness": 4.0}
    assert report["weights"]["completeness"] == 4.0


def test_score_llm_rerank_success_and_fallbacks(tmp_path: Path) -> None:
    from videoflow.steps.shorts_score import ScoreParams, ShortsScoreStep

    class FakeLlm:
        def __init__(self, payload: object = None, *, raises: bool = False) -> None:
            self.payload = payload
            self.raises = raises
            self.prompts: list[str] = []

        def complete_json(self, prompt: str, purpose: str) -> object:
            self.prompts.append(prompt)
            if self.raises:
                raise RuntimeError("llm offline")
            return self.payload

    clips = [make_clip("one alpha"), make_clip("two beta"), make_clip("three gamma")]
    single = make_context(tmp_path / "single", selected_shorts=[clips[0]])
    ShortsScoreStep().run(
        single,
        ScoreParams(use_llm=True),
        StepIO(llm_client=FakeLlm({"ranking": [0]})),
    )
    assert len(single.selected_shorts) == 1

    for payload in ({"ranking": [2]}, {"ranking": "nope"}):
        context = make_context(
            tmp_path / f"payload-{str(payload)[:12]}",
            selected_shorts=list(clips),
        )
        llm = FakeLlm(payload)
        ShortsScoreStep().run(context, ScoreParams(use_llm=True), StepIO(llm_client=llm))
        titles = [clip.title for clip in context.selected_shorts]
        assert len(titles) == 3
        assert llm.prompts

    ordered = make_context(tmp_path / "ordered", selected_shorts=list(clips))
    ShortsScoreStep().run(
        ordered,
        ScoreParams(use_llm=True),
        StepIO(llm_client=FakeLlm({"ranking": [2, 99]})),
    )
    assert ordered.selected_shorts[0].title == "three gamma"

    failing = make_context(tmp_path / "failing", selected_shorts=list(clips))
    ShortsScoreStep().run(
        failing,
        ScoreParams(use_llm=True),
        StepIO(llm_client=FakeLlm(raises=True)),
    )
    assert len(failing.selected_shorts) == 3


# ---------------------------------------------------------------------------
# transcribe.py
# ---------------------------------------------------------------------------


class FakeAsr:
    def __init__(self, sentences: list[Sentence] | None = None) -> None:
        self.sentences = sentences
        self.calls: list[tuple[Path, int]] = []

    def transcribe(self, wav: Path, sample_rate: int) -> list[Sentence]:
        self.calls.append((wav, sample_rate))
        if self.sentences is None:
            return [sentence(0, 0, 48000, "spoken")]
        return self.sentences


class FakePcmAdapter:
    def extract_pcm(
        self,
        source: Path,
        destination: Path,
        *,
        sample_rate: int = 16000,
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"RIFF")
        return destination


def test_transcribe_none_project_and_srt_modes(tmp_path: Path) -> None:
    from videoflow.steps.transcribe import TranscribeParams, TranscribeStep

    context = make_context(tmp_path, media_info=make_media(tmp_path))
    TranscribeStep().run(context, TranscribeParams(mode="none"), StepIO())
    assert context.transcript == []
    assert context.transcript_source == "none"

    with pytest.raises(IngestError, match="No project transcript"):
        TranscribeStep().run(context, TranscribeParams(mode="project"), StepIO())

    context.transcript = [sentence(0, 0, 48000, "from project")]
    TranscribeStep().run(context, TranscribeParams(mode="auto"), StepIO())
    assert context.transcript_source == "project"

    subtitle = tmp_path / "subs.srt"
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nHello there.\n",
        encoding="utf-8",
    )
    context.media = make_media(tmp_path)
    context.transcript = []
    TranscribeStep().run(context, TranscribeParams(srt_path=str(subtitle)), StepIO())
    assert context.transcript_source == "srt"
    assert context.transcript[0].text == "Hello there."
    assert context.hashes["transcribe"]

    with pytest.raises(IngestError, match="Subtitle file does not exist"):
        TranscribeStep().run(
            context,
            TranscribeParams(mode="srt", srt_path=str(tmp_path / "missing.srt")),
            StepIO(),
        )


def test_transcribe_rejects_an_empty_parsed_srt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps import transcribe as transcribe_module
    from videoflow.steps.transcribe import TranscribeParams, TranscribeStep

    context = make_context(tmp_path, media_info=make_media(tmp_path))
    subtitle = tmp_path / "empty.srt"
    subtitle.write_text("1\n", encoding="utf-8")
    monkeypatch.setattr(transcribe_module, "parse_srt_file", lambda path, rate: [])
    with pytest.raises(TranscriptionError, match="no usable sentences"):
        TranscribeStep().run(
            context,
            TranscribeParams(mode="srt", srt_path=str(subtitle)),
            StepIO(),
        )


def test_transcribe_auto_mode_without_engine_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps import transcribe as transcribe_module
    from videoflow.steps.transcribe import TranscribeParams, TranscribeStep

    monkeypatch.setattr(
        transcribe_module.FasterWhisperAdapter,
        "available",
        staticmethod(lambda model_size="small", *, model=None: False),
    )
    for name in (
        "VIDEOWFLOW_WHISPER_BIN",
        "VIDEOWFLOW_WHISPER_MODEL",
        "VIDEOWFLOW_ASR_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("videoflow.application.models.list_models", lambda: [])
    context = make_context(tmp_path, media_info=make_media(tmp_path))
    emitted: list[str] = []
    TranscribeStep().run(
        context,
        TranscribeParams(mode="auto", quality_profile="custom"),
        StepIO(log=lambda module, level, message: emitted.append(message)),
    )
    assert context.transcript_source == "none"
    assert context.warnings and "Transcription skipped" in context.warnings[-1]
    assert any("No speech-to-text engine" in message for message in emitted)


def test_transcribe_available_mode_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps import transcribe as transcribe_module
    from videoflow.steps.transcribe import TranscribeStep

    context = make_context(tmp_path, media_info=make_media(tmp_path))
    io = StepIO()
    monkeypatch.setattr(
        transcribe_module.FasterWhisperAdapter,
        "available",
        staticmethod(lambda model_size="small", *, model=None: True),
    )
    assert TranscribeStep._available_mode(context, io) == "faster_whisper"

    monkeypatch.setattr(
        transcribe_module.FasterWhisperAdapter,
        "available",
        staticmethod(lambda model_size="small", *, model=None: False),
    )
    monkeypatch.setenv("VIDEOWFLOW_WHISPER_BIN", "/usr/bin/whisper")
    assert TranscribeStep._available_mode(context, io) == "whisper_cpp"

    monkeypatch.delenv("VIDEOWFLOW_WHISPER_BIN")
    monkeypatch.setenv("VIDEOWFLOW_WHISPER_MODEL", "/models/ggml.bin")
    assert TranscribeStep._available_mode(context, io) == "whisper_cpp"

    monkeypatch.delenv("VIDEOWFLOW_WHISPER_MODEL")
    monkeypatch.setattr("videoflow.application.models.list_models", lambda: [])
    monkeypatch.setattr("videoflow.runtime.find_whisper_binary", lambda: None)
    monkeypatch.setenv("VIDEOWFLOW_ASR_BASE_URL", "http://asr.local/v1")
    assert TranscribeStep._available_mode(context, io) == "http"


def test_transcribe_http_client_and_cache_put(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps import transcribe as transcribe_module
    from videoflow.steps.transcribe import TranscribeParams, TranscribeStep

    calls: dict[str, object] = {}

    class FakeHttp:
        def __init__(self, **kwargs: object) -> None:
            calls["http"] = kwargs

        def transcribe(self, wav: Path, sample_rate: int) -> list[Sentence]:
            calls["wav"] = wav
            return [sentence(0, 0, 48000, "over http")]

    monkeypatch.setattr(transcribe_module, "WhisperHttpAdapter", FakeHttp)
    context = make_context(tmp_path, media_info=make_media(tmp_path))
    context.pcm_digest = "pcm-digest"
    TranscribeStep().run(
        context,
        TranscribeParams(mode="http", base_url="http://asr.local/v1"),
        StepIO(adapter=FakePcmAdapter()),
    )
    assert calls["http"]["base_url"] == "http://asr.local/v1"
    assert context.transcript_source == "http"
    assert context.transcript[0].text == "over http"
    assert context.cache_misses == ["transcribe"]
    assert context.hashes["transcribe"]

    with pytest.raises(TranscriptionError, match="requires base_url"):
        TranscribeStep().run(
            context,
            TranscribeParams(mode="http", base_url=None),
            StepIO(adapter=FakePcmAdapter()),
        )

    empty = make_context(tmp_path / "empty", media_info=make_media(tmp_path / "empty"))
    with pytest.raises(TranscriptionError, match="returned no sentences"):
        TranscribeStep().run(
            empty,
            TranscribeParams(mode="http", base_url="http://asr.local/v1"),
            StepIO(asr_client=FakeAsr(sentences=[]), adapter=FakePcmAdapter()),
        )


def test_transcribe_whisper_and_faster_clients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps import transcribe as transcribe_module
    from videoflow.steps.transcribe import TranscribeParams, TranscribeStep

    calls: dict[str, object] = {}

    class FakeCli:
        def __init__(self, **kwargs: object) -> None:
            calls["cli"] = kwargs

        def transcribe(self, wav: Path, sample_rate: int) -> list[Sentence]:
            return [sentence(0, 0, 48000, "over cli")]

    class FakeFaster:
        def __init__(self, **kwargs: object) -> None:
            calls["faster"] = kwargs

        @staticmethod
        def available(model_size: str = "small", *, model: object = None) -> bool:
            return False

        def transcribe(self, wav: Path, sample_rate: int) -> list[Sentence]:
            return [sentence(0, 0, 48000, "over faster")]

    monkeypatch.setattr(transcribe_module, "WhisperCliAdapter", FakeCli)
    monkeypatch.setenv("VIDEOWFLOW_WHISPER_BIN", "/usr/bin/whisper")
    cli_context = make_context(tmp_path / "cli", media_info=make_media(tmp_path / "cli"))
    TranscribeStep().run(
        cli_context,
        TranscribeParams(mode="whisper_cpp"),
        StepIO(adapter=FakePcmAdapter()),
    )
    assert calls["cli"]["binary"] == "/usr/bin/whisper"
    assert cli_context.transcript_source == "whisper_cpp"

    monkeypatch.setattr(transcribe_module, "FasterWhisperAdapter", FakeFaster)
    faster_context = make_context(tmp_path / "faster", media_info=make_media(tmp_path / "faster"))
    TranscribeStep().run(
        faster_context,
        TranscribeParams(mode="faster_whisper", model_size="tiny", language="en"),
        StepIO(adapter=FakePcmAdapter()),
    )
    assert calls["faster"]["language"] == "en"
    assert faster_context.transcript[0].text == "over faster"


def test_transcribe_reports_faster_whisper_progress(tmp_path: Path) -> None:
    from videoflow.steps.transcribe import TranscribeParams, TranscribeStep

    class FakeClient:
        def transcribe(
            self,
            wav: Path,
            sample_rate: int,
            *,
            on_progress: object = None,
        ) -> list[Sentence]:
            assert callable(on_progress)
            on_progress(0.5, 1.0)  # type: ignore[operator]
            return [sentence(0, 0, 48000, "progress")]

    context = make_context(tmp_path, media_info=make_media(tmp_path))
    reported: list[tuple[str, int, str]] = []
    TranscribeStep().run(
        context,
        TranscribeParams(mode="faster_whisper", model_size="tiny", language="en"),
        StepIO(
            adapter=FakePcmAdapter(),
            asr_client=FakeClient(),
            progress=lambda stage, percent, message: reported.append((stage, percent, message)),
        ),
    )

    assert any(percent == 72 for _, percent, _ in reported)
    assert context.transcript[0].text == "progress"


def test_transcribe_resumes_from_a_partial_checkpoint(tmp_path: Path) -> None:
    from videoflow.steps.transcribe import TranscribeParams, TranscribeStep

    context = make_context(tmp_path, media_info=make_media(tmp_path))
    context.pcm_digest = "digest"
    partial_path = context.work / "transcribe.partial.json"
    partial_path.write_text(
        json.dumps(
            {
                "source": "digest",
                "sentences": [sentence(0, 0, 48000, "head").model_dump(mode="json")],
            }
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self) -> None:
            self.offset = -1
            self.initial = 0

        def transcribe(
            self,
            wav: Path,
            sample_rate: int,
            *,
            initial_sentences: list[Sentence] | None = None,
            offset_samples: int = 0,
            on_segment: object = None,
            on_progress: object = None,
        ) -> list[Sentence]:
            self.offset = offset_samples
            self.initial = len(initial_sentences or [])
            new = sentence(1, 48000, 96000, "tail")
            assert callable(on_segment)
            on_segment(new)  # type: ignore[operator]
            payload = json.loads(partial_path.read_text(encoding="utf-8"))
            assert payload["sentences"][-1]["text"] == "tail"
            return [*(initial_sentences or []), new]

    client = FakeClient()
    TranscribeStep().run(
        context,
        TranscribeParams(mode="faster_whisper", model_size="tiny", language="en"),
        StepIO(adapter=FakePcmAdapter(), asr_client=client),
    )

    assert client.initial == 1
    assert client.offset == 48000
    assert [item.text for item in context.transcript] == ["head", "tail"]
    assert not partial_path.exists()


def test_transcribe_warns_about_large_models_on_cpu(tmp_path: Path) -> None:
    from videoflow.steps.transcribe import TranscribeParams, TranscribeStep

    class FakeClient:
        def transcribe(self, wav: Path, sample_rate: int) -> list[Sentence]:
            return [sentence(0, 0, 48000, "large")]

    context = make_context(tmp_path, media_info=make_media(tmp_path))
    emitted: list[tuple[str, str]] = []
    TranscribeStep().run(
        context,
        TranscribeParams(
            mode="faster_whisper",
            model_size="large-v3",
            device="cpu",
            language="en",
        ),
        StepIO(
            adapter=FakePcmAdapter(),
            asr_client=FakeClient(),
            log=lambda module, level, message: emitted.append((level, message)),
        ),
    )

    assert any(level == "warning" and "slow on CPU" in message for level, message in emitted)


def test_transcribe_settings_are_applied_and_errors_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps.transcribe import TranscribeParams, TranscribeStep

    context = make_context(
        tmp_path,
        media_info=make_media(tmp_path),
        transcript=[sentence(0, 0, 48000, "ready")],
    )

    def broken_settings() -> object:
        raise RuntimeError("settings exploded")

    monkeypatch.setattr("videoflow.application.settings.load_settings", broken_settings)
    TranscribeStep().run(context, TranscribeParams(mode="project"), StepIO())
    assert context.transcript_source == "project"

    settings = SimpleNamespace(
        models=SimpleNamespace(defaults={"asr": "whisper-medium"}),
        speech=SimpleNamespace(
            device="cuda",
            compute_type="float16",
            language="en",
            vad_filter=True,
        ),
    )
    monkeypatch.setattr("videoflow.application.settings.load_settings", lambda: settings)
    TranscribeStep().run(context, TranscribeParams(mode="project"), StepIO())
    assert context.transcript_source == "project"
    TranscribeStep().run(
        context,
        TranscribeParams(
            mode="project",
            device="auto",
            compute_type="float32",
            language="es",
            vad_filter=True,
        ),
        StepIO(),
    )
    assert context.transcript_source == "project"


def test_transcribe_cached_sentences_and_invalid_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps import transcribe as transcribe_module
    from videoflow.steps.transcribe import TranscribeParams, TranscribeStep

    context = make_context(tmp_path, media_info=make_media(tmp_path))
    context.pcm_digest = "pcm-digest"
    payloads: dict[str, dict[str, object]] = {
        "invalid": {"sentences": [{"nope": True}], "source": "http"},
        "empty": {"sentences": [], "source": "http"},
    }

    def fake_cache_get(kind: str, key: str) -> dict[str, object] | None:
        return payloads["invalid"]

    monkeypatch.setattr(transcribe_module, "cache_get", fake_cache_get)
    monkeypatch.setattr(transcribe_module, "cache_put", lambda kind, key, payload: None)
    asr = FakeAsr(sentences=[sentence(0, 0, 48000, "fresh")])
    TranscribeStep().run(
        context,
        TranscribeParams(mode="http", base_url="http://asr.local/v1"),
        StepIO(asr_client=asr, adapter=FakePcmAdapter()),
    )
    assert context.transcript[0].text == "fresh"
    assert context.cache_hits == []

    payloads["invalid"] = payloads["empty"]
    empty_context = make_context(tmp_path / "empty", media_info=make_media(tmp_path / "empty"))
    empty_context.pcm_digest = "pcm-digest"
    TranscribeStep().run(
        empty_context,
        TranscribeParams(mode="http", base_url="http://asr.local/v1"),
        StepIO(asr_client=asr, adapter=FakePcmAdapter()),
    )
    assert empty_context.transcript[0].text == "fresh"
    assert empty_context.cache_hits == []

    monkeypatch.setattr(
        transcribe_module,
        "cache_get",
        lambda kind, key: {
            "sentences": [sentence(0, 0, 48000, "cached").model_dump(mode="json")],
            "source": "http",
        },
    )
    hit_context = make_context(tmp_path / "hit", media_info=make_media(tmp_path / "hit"))
    hit_context.pcm_digest = "pcm-digest"
    TranscribeStep().run(
        hit_context,
        TranscribeParams(mode="http", base_url="http://asr.local/v1"),
        StepIO(asr_client=asr, adapter=FakePcmAdapter()),
    )
    assert hit_context.transcript[0].text == "cached"
    assert hit_context.cache_hits == ["transcribe"]


def test_transcribe_requires_media(tmp_path: Path) -> None:
    from videoflow.steps.transcribe import TranscribeParams, TranscribeStep

    context = make_context(tmp_path)
    with pytest.raises(IngestError, match="ingest step"):
        TranscribeStep().run(context, TranscribeParams(mode="none"), StepIO())


def test_transcribe_uses_an_installed_asr_model_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.application import models
    from videoflow.steps import transcribe as transcribe_module
    from videoflow.steps.transcribe import TranscribeParams, TranscribeStep

    model_path = tmp_path / "faster-whisper-tiny"
    model_path.mkdir()
    monkeypatch.setattr(
        models,
        "list_models",
        lambda: [
            {
                "id": "faster-whisper-tiny",
                "label": "Faster-Whisper tiny",
                "capability": "asr",
                "kind": "faster-whisper",
                "installed": True,
            }
        ],
    )
    monkeypatch.setattr(models, "installed_path", lambda _model_id: model_path)
    calls: dict[str, object] = {}

    class FakeFaster:
        def __init__(self, **kwargs: object) -> None:
            calls["faster"] = kwargs

        def transcribe(self, wav: Path, sample_rate: int) -> list[Sentence]:
            return [sentence(0, 0, 48000, "model id")]

    monkeypatch.setattr(transcribe_module, "FasterWhisperAdapter", FakeFaster)
    context = make_context(tmp_path / "model", media_info=make_media(tmp_path / "model"))
    TranscribeStep().run(
        context,
        TranscribeParams(model_id="faster-whisper-tiny", mode="auto"),
        StepIO(adapter=FakePcmAdapter()),
    )
    assert calls["faster"]["model"] == model_path
    assert context.transcript_source == "faster_whisper"


def test_transcribe_rejects_an_uninstalled_model_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.application import models
    from videoflow.domain.errors import TranscriptionError
    from videoflow.steps.transcribe import TranscribeParams, TranscribeStep

    monkeypatch.setattr(
        models,
        "list_models",
        lambda: [
            {
                "id": "faster-whisper-tiny",
                "label": "Faster-Whisper tiny",
                "capability": "asr",
                "kind": "faster-whisper",
                "installed": False,
            }
        ],
    )
    monkeypatch.setattr(models, "installed_path", lambda _model_id: None)
    context = make_context(tmp_path / "missing", media_info=make_media(tmp_path / "missing"))
    with pytest.raises(TranscriptionError, match="not installed"):
        TranscribeStep().run(
            context,
            TranscribeParams(model_id="faster-whisper-tiny", mode="auto"),
            StepIO(adapter=FakePcmAdapter()),
        )


def test_audio_master_renders_the_timeline_when_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps import content_audio
    from videoflow.steps.content import AudioMasterParams, AudioMasterStep

    context = make_context(tmp_path)
    media = make_media(tmp_path)
    context.media = media
    context.state = ProjectState(
        sources={"src1": media},
        audio_segments=[
            AudioSegment(
                clip_id="a1",
                source_id="src1",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            )
        ],
    )
    calls: list[tuple[ProjectState, Path]] = []

    def fake_export(state, target, **kwargs):
        calls.append((state, target))
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_bytes(b"timeline-master")
        return Path(target)

    monkeypatch.setattr(content_audio, "export_timeline_audio", fake_export)
    AudioMasterStep().run(context, AudioMasterParams(), StepIO())

    assert calls and calls[0][0] is context.state
    assert (tmp_path / "out" / "audio" / "master.wav").read_bytes() == b"timeline-master"


def test_audio_master_timeline_guards_and_source_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.steps import content_audio
    from videoflow.steps.content import AudioMasterParams, AudioMasterStep

    monkeypatch.setattr(content_audio, "FFmpegAdapter", _FakeFFmpeg)
    context = make_context(tmp_path)
    context.media = make_media(tmp_path)
    with pytest.raises(ExportError, match="no timeline exists"):
        AudioMasterStep().run(context, AudioMasterParams(source="timeline"), StepIO())

    media = context.media
    context.state = ProjectState(
        sources={"src1": media},
        audio_segments=[
            AudioSegment(
                clip_id="a1",
                source_id="src1",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            )
        ],
    )
    AudioMasterStep().run(context, AudioMasterParams(source="source"), StepIO())
    assert any("used the source" in item for item in context.warnings)
