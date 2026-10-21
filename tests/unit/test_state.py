import uuid

import pytest
from pydantic import ValidationError

from videoflow.domain.config import (
    RetakesConfig,
    ShortsConfig,
    TranscribeConfig,
    ZoomsConfig,
)
from videoflow.domain.state import (
    ApiError,
    AudioSegment,
    JobRecord,
    LlmRetakeResponse,
    ManualOverride,
    MediaInfo,
    ProjectState,
    SampleSpan,
    Sentence,
    Transform,
    VerticalClip,
    VideoSegment,
    WordTiming,
)


def test_cpu_first_defaults_satisfy_the_acceptance_gate() -> None:
    config = TranscribeConfig()
    assert (config.device, config.compute_type, config.model_size) == ("cpu", "int8", "small")


def test_retakes_config_forbids_a_raw_api_key() -> None:
    with pytest.raises(ValidationError):
        RetakesConfig(api_key="secret")  # type: ignore[call-arg]


def test_zoom_scale_is_bounded() -> None:
    with pytest.raises(ValidationError):
        ZoomsConfig(punch_in_scale=2.0)


def test_shorts_window_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        ShortsConfig(target_duration_min_sec=90, target_duration_max_sec=30)
    with pytest.raises(ValidationError):
        ShortsConfig(source_start_sec=10, source_end_sec=5)


def test_media_info_schema_has_rational_time_and_no_derived_float() -> None:
    info = MediaInfo(
        source_path="/media/take.mp4",
        duration_frames=1080,
        fps_num=30000,
        fps_den=1001,
        width=3840,
        height=2160,
        audio_sample_rate=48000,
    )
    assert info.timebase().frame_duration.denominator == 30000
    assert "duration_sec" not in info.model_dump()


def test_project_state_rejects_duplicate_sentence_ids() -> None:
    sentence = Sentence(id=1, start_sample=0, end_sample=10, text="one")
    with pytest.raises(ValidationError):
        ProjectState(transcript=[sentence, sentence])


def test_state_is_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        MediaInfo(
            source_path="/a.mp4",
            duration_frames=1,
            fps_num=30,
            fps_den=1,
            width=2,
            height=2,
            audio_sample_rate=48000,
            api_key="nope",  # type: ignore[call-arg]
        )


def test_all_state_validators_accept_valid_ranges() -> None:
    assert SampleSpan(start_sample=0, end_sample=1)
    assert WordTiming(word="hi", start_sample=0, end_sample=1, probability=0.5)
    assert Sentence(id=0, start_sample=0, end_sample=1, text="hi")
    assert ManualOverride(sentence_id=0, action="discard")
    assert Transform(scale=1.15, type="punch_in")
    assert VideoSegment(
        clip_id="c1",
        source_in_frame=0,
        source_out_frame=10,
        timeline_in_frame=0,
        timeline_out_frame=10,
    )
    assert AudioSegment(
        clip_id="c1",
        source_in_sample=0,
        source_out_sample=10,
        timeline_in_sample=0,
        timeline_out_sample=10,
    )
    assert VerticalClip(clip_id="v1", title="Hook", start_sample=0, end_sample=10)


@pytest.mark.parametrize(
    ("factory",),
    [
        (lambda: SampleSpan(start_sample=10, end_sample=10),),
        (lambda: WordTiming(word="x", start_sample=10, end_sample=1, probability=0.2),),
        (lambda: Sentence(id=0, start_sample=10, end_sample=1, text="x"),),
        (
            lambda: VideoSegment(
                clip_id="c",
                source_in_frame=10,
                source_out_frame=10,
                timeline_in_frame=0,
                timeline_out_frame=1,
            ),
        ),
        (
            lambda: VideoSegment(
                clip_id="c",
                source_in_frame=0,
                source_out_frame=1,
                timeline_in_frame=4,
                timeline_out_frame=1,
            ),
        ),
        (
            lambda: AudioSegment(
                clip_id="c",
                source_in_sample=10,
                source_out_sample=10,
                timeline_in_sample=0,
                timeline_out_sample=1,
            ),
        ),
        (
            lambda: AudioSegment(
                clip_id="c",
                source_in_sample=0,
                source_out_sample=1,
                timeline_in_sample=9,
                timeline_out_sample=1,
            ),
        ),
        (lambda: VerticalClip(clip_id="v", title="t", start_sample=4, end_sample=4),),
    ],
)
def test_state_validators_reject_inverted_ranges(factory: object) -> None:
    with pytest.raises(ValidationError):
        factory()  # type: ignore[operator]


def test_llm_response_requires_reasoning() -> None:
    with pytest.raises(ValidationError):
        LlmRetakeResponse(discard_sentence_ids=[], reasoning="")


def test_api_error_is_always_not_ok() -> None:
    error = ApiError(code="x", message="y")
    assert error.ok is False
    assert error.details == {}


def test_job_record_shape() -> None:
    job = JobRecord(
        job_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        status="queued",
    )
    assert job.active_module is None


def test_state_round_trips_json() -> None:
    state = ProjectState()
    restored = ProjectState.model_validate_json(state.model_dump_json())
    assert restored.project_id == state.project_id
    assert restored.schema_version == 1
