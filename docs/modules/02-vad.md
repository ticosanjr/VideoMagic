# Module 02 — Voice activity detection

## Implementation status

The portable build uses FFmpeg `silencedetect` (`FFmpegAdapter.detect_speech`)
and complements the silence spans. It needs no model and is the engine behind
`videoflow run`/`demo`. Silero ONNX remains the quality path and is specified
below; it is not implemented yet.

## Purpose

Find speech in the analysis WAV and produce the intervals that the cut engine
will keep. VAD decides cuts; Whisper only timestamps.

## Inputs

- `work/source.wav`.
- `VadConfig`.

## Outputs

- `vad_intervals`: half-open sample spans in source time.
- A summary: intervals found, speech seconds, silence seconds pruned.

## Configuration

| Key | Default | Range | Meaning |
| --- | --- | --- | --- |
| `speech_threshold` | 0.5 | 0.1–0.9 | Speech probability threshold |
| `min_silence_duration_ms` | 400 | ≥ 0 | Pauses shorter than this are kept |
| `speech_pad_before_ms` | 120 | ≥ 0 | Keeps plosive onsets |
| `speech_pad_after_ms` | 150 | ≥ 0 | Keeps trailing consonants |
| `keep_handles_ms` | 200 | ≥ 0 | Hidden media for J/L-cuts |

## Algorithm

1. Load Silero VAD ONNX. CPU by default; CUDA optional.
2. Run 30 ms windows. Produce a probability per window.
3. Threshold, then group speech windows.
4. Fill gaps shorter than `min_silence_duration_ms`.
5. Apply pads in samples and clamp to `[0, duration]`.
6. Expand each padded interval to covering frames with `Timebase.apply_pads`.
7. Keep `keep_handles_ms` around the frame span for later offsets.
8. Persist sample spans plus the frame spans used by the cut engine.

## Failure modes

| Failure | Behaviour |
| --- | --- |
| No speech found | Fail with `no_speech`; never export an empty timeline |
| All speech | One interval; cuts come only from retakes |
| Clip shorter than the minimum | Keep one interval covering the clip |
| Pads collapse | `InvalidTimeError` |
| ONNX runtime missing | Fail with an install hint, not a traceback |

## Cache

Depends on the PCM fingerprint and every VAD parameter. Changing the threshold
invalidates VAD and everything after it.

## Tests

| Id | Case |
| --- | --- |
| T-02-01 | Tone-gated fixture yields the expected interval count |
| T-02-02 | A 200 ms gap is kept when the minimum is 400 ms |
| T-02-03 | A 500 ms gap is cut when the minimum is 400 ms |
| T-02-04 | Pads never cross sample zero or the media end |
| T-02-05 | Frame spans fully cover padded samples |
| T-02-06 | No speech raises a typed error |
| T-02-07 | Handles are recorded but not played |

AC: 01, 02, 05.
