from __future__ import annotations

import struct
import wave
from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, Sentence, WordTiming
from videoflow.steps.base import StepIO
from videoflow.steps.timeline import TimelineParams, TimelineStep, _pcm_rms


def _write_wav(path: Path, samples: list[int], rate: int = 48_000) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(struct.pack("<h", value) for value in samples))


def test_pcm_rms_reads_samples_and_handles_bad_paths(tmp_path: Path) -> None:
    path = tmp_path / "tone.wav"
    _write_wav(path, [1_000] * 48_000)
    with _pcm_rms(path) as rms:
        assert rms is not None
        assert rms(0, 48_000) > 900
        assert rms(-10, 48_000) > 0
        assert rms(0, 0) >= 0
    with _pcm_rms(None) as rms:
        assert rms is None
    with _pcm_rms(tmp_path / "missing.wav") as rms:
        assert rms is None
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"not a wave")
    with _pcm_rms(broken) as rms:
        assert rms is None


def test_timeline_step_uses_word_runs_and_pcm_energy(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    pcm = tmp_path / "source.wav"
    # 1s tone, 1s silence, 1s tone.
    _write_wav(pcm, [1_000] * 48_000 + [0] * 48_000 + [1_000] * 48_000)
    media = MediaInfo(
        source_path=str(source),
        duration_frames=90,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48_000,
    )
    context = PipelineContext(
        source=source,
        output=tmp_path / "out",
        work=tmp_path,
        exports=tmp_path / "exports",
        media=media,
        pcm_path=pcm,
    )
    context.metadata["transcript_normalized"] = True
    context.transcript = [
        Sentence(
            id=0,
            start_sample=0,
            end_sample=144_000,
            text="one two",
            words=[
                WordTiming(
                    word="one",
                    start_sample=0,
                    end_sample=24_000,
                    probability=0.9,
                ),
                WordTiming(
                    word="two",
                    start_sample=120_000,
                    end_sample=144_000,
                    probability=0.9,
                ),
            ],
        )
    ]
    TimelineStep().run(
        context,
        TimelineParams(
            use_transcript_spans=True,
            max_internal_gap_ms=150,
            internal_gap_mode="smart",
            gap_energy_threshold=800,
            long_gap_ms=500,
        ),
        StepIO(),
    )
    assert context.state is not None
    assert len(context.state.video_segments) == 2
    assert context.state.video_segments[0].source_out_frame < 60
