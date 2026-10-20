# Module 02 — Voice activity detection

## Implementation status

Silero VAD v5.1.2 runs through ONNX Runtime on the CPU and is the quality path.
The portable build bundles the 2.3 MB model; `videoflow run`, jobs, the project
API, and MCP `videoflow_run_vad` select it by default when it is available.
FFmpeg `silencedetect` remains the fallback for development checkouts and
unsupported platforms.

Engine selection is explicit and typed:

| `vad_engine` | Behaviour |
| --- | --- |
| `auto` (default) | Silero when the model and `onnxruntime` import; otherwise FFmpeg |
| `silero` | Require Silero; fail with an install/model hint when unavailable |
| `ffmpeg` | Force the model-free FFmpeg detector |

## Purpose

Find speech in the analysis audio and produce the intervals that the cut engine
will keep. VAD decides cuts; Whisper only timestamps.

## Inputs

- `work/source.wav`: analysis PCM at the source audio rate, used by FFmpeg.
- `work/vad.wav`: 16 kHz mono PCM, extracted only for Silero.
- `VadConfig` plus the run-level `min_speech_ms`.

## Outputs

- `vad_intervals`: half-open sample spans in source time.
- `vad_engine` in `run.json` and job results (`silero` or `ffmpeg`).
- Progress/log summaries: intervals found and the selected engine.

## Configuration

| Key | Default | Range | Meaning |
| --- | --- | --- | --- |
| `engine` | `auto` | auto/silero/ffmpeg | Detector selection |
| `speech_threshold` | 0.5 | 0.1–0.9 | Silero speech probability threshold |
| `min_silence_duration_ms` | 400 | ≥ 0 | Pauses shorter than this are kept |
| `speech_pad_before_ms` | 120 | ≥ 0 | Keeps plosive onsets |
| `speech_pad_after_ms` | 150 | ≥ 0 | Keeps trailing consonants |
| `keep_handles_ms` | 200 | ≥ 0 | Hidden media for J/L-cuts |

`noise_db` applies to the FFmpeg fallback only. Pads apply to both engines and
are added after retake culling, so a culled take cannot survive as pad-only
audio.

## Algorithm

1. Probe the media and extract `work/source.wav` at the source sample rate.
2. Select the engine. `auto` prefers Silero when both the pinned model and
   `onnxruntime` are available.
3. Silero path: extract a second mono 16 kHz WAV, run 512-sample (32 ms) windows
   with the LSTM state carried between windows, and compare each probability to
   `speech_threshold`.
4. Group active windows, fill gaps shorter than `min_silence_duration_ms`, and
   drop spans shorter than `min_speech_ms`.
5. Map 16 kHz spans to the source rate with exact integer floor/ceil arithmetic;
   the end is rounded up so coverage is never lost.
6. Apply pads in source samples and clamp to `[0, duration]`.
7. Merge overlaps and persist half-open sample spans. The timeline builder
   expands padded spans to covering frames.
8. Keep `keep_handles_ms` as the unplayed gap available to J/L offsets; handles
   are not added to the speech span.

## Failure modes

| Failure | Behaviour |
| --- | --- |
| No speech found | Fail with `ingest_failed`; never export an empty timeline |
| All speech | One interval; cuts come only from retakes |
| Speech shorter than `min_speech_ms` | Every span is dropped; the empty result fails with `ingest_failed` |
| Pads clipped at media bounds | Pads clamp; empty spans are dropped |
| ONNX Runtime missing | `auto` falls back; explicit `silero` fails with an install hint |
| Model missing | Explicit `silero` fails with the expected path and fetch hint |
| Model load failure | Explicit `silero` fails with the inference/load error |
| Wrong WAV rate or layout | Typed `ingest_failed` before inference |

## Cache

Depends on the PCM fingerprint and every VAD parameter, including `engine`.
Changing the threshold or pads invalidates VAD and everything after it.

## Automated coverage

| Test | Case |
| --- | --- |
| `tests/unit/test_silero.py` | Window probabilities, short-gap merging, contiguous windows at `min_silence_ms=0`, minimum-speech filtering, 16 kHz validation, missing model |
| `tests/unit/test_vad_engine.py` | Floor/ceil rescaling, pad clamping/merging, auto fallback, Silero selection, explicit failure |
| `tests/unit/test_portable.py` | Silero extraction at 16 kHz, source-rate intervals, pads after retake culling |
| `tests/contract/test_mcp_live.py` | Live FFmpeg VAD path with deterministic fake detection |
| `tests/unit/test_runtime.py` | Bundled and environment model discovery |

AC: 01, 02, 05.
