# Module 03 — Transcription

## Implementation status

Implemented: SRT import, an OpenAI-compatible `/audio/transcriptions` client,
the bundled whisper.cpp CLI, and a local Faster-Whisper 1.2.1/CTranslate2
adapter with word timestamps. Release builds bundle the pinned
`Systran/faster-whisper-small` model. Larger CTranslate2 models remain available
through a local model directory.

## Purpose

Produce a sentence and word transcript with source-sample timestamps that do not
drift over an hour.

## Inputs

- The complete source media. Local engines receive `work/transcribe.wav`, a
  16 kHz mono WAV extracted from the full source, never from pre-sliced VAD
  intervals. The ASR path posts the analysis WAV at the source sample rate.
- `TranscribeConfig`.
- Optional local model paths.

## Outputs

- `state.transcript`: sentences with ids, sample spans, text, and words.
- Word probabilities for the inspector and for low-confidence warnings.
- `transcript_source`: `srt`, `asr`, `whisper`, `faster-whisper`, or `project`.

## Configuration

| Key | Default | Meaning |
| --- | --- | --- |
| `engine` | `auto` | `auto`, `faster-whisper`, or `whisper.cpp` |
| `model_size` | `small` | tiny/base/small/medium/large-v3 |
| `language` | `pt` | pt/it/en/es/auto |
| `device` | `cpu` | cpu/cuda |
| `compute_type` | `int8` | int8/float16/float32 |
| `vad_filter` | `false` | Faster-Whisper's own VAD; keep off when module 02 is enabled |

CPU is the default. `large-v3` is available to an operator who installs that
CTranslate2 model, but it is not bundled. CUDA and float16 are opt-in.

### Engine selection

`auto` prefers Faster-Whisper when both the optional Python package and the
selected local model directory are present. Otherwise it uses whisper.cpp. An
explicit `faster-whisper` or `whisper.cpp` request never silently downgrades:
a missing package, model, or CUDA runtime fails with an actionable message.

An `asr_base_url` still takes precedence over both local engines. An SRT or a
project transcript takes precedence over every engine.

### Local models

The adapter never downloads a model implicitly. It resolves a CTranslate2 model
directory in this order:

1. `VIDEOWFLOW_FASTER_WHISPER_MODEL` (an explicit model directory)
2. `<bundle>/faster-whisper/<size>`
3. `<bundle>/vendor/faster-whisper/<size>`
4. Next to the executable: `faster-whisper/<size>`
5. `<portable home>/models/faster-whisper/<size>`

A valid directory contains `model.bin` and `config.json`. Fetch the pinned
small model with `uv run python scripts/fetch_faster_whisper.py`; portable
release builds add it with `--with-faster-whisper`. For another size, convert a
Whisper checkpoint to CTranslate2 or download a compatible model directory and
point `VIDEOWFLOW_FASTER_WHISPER_MODEL` at it.

whisper.cpp continues to use a GGML model: `whisper_model`, then
`VIDEOWFLOW_WHISPER_MODEL`, then the bundled `ggml-tiny.bin`.

## Algorithm

1. Load Faster-Whisper with the selected model, device, and compute type.
2. Transcribe the full WAV. Do not pre-slice by VAD intervals.
3. Faster-Whisper is asked for word timestamps. If a returned segment has no
   usable word times, fail; the quality path must not fabricate them. The
   whisper.cpp and ASR paths keep their sentence-level contract and may return
   an empty `words` list.
4. Convert word times to source samples with `Fraction`, then `floor` for starts
   and `ceil` for ends.
5. Group words into sentences. Sentence ids are sequential integers starting at
   zero and are stable for a given transcript.
6. Preserve recognised wording and punctuation; trim outer whitespace only. The
   UI and prompts do the normalisation.
7. Persist. Never mutate an existing transcript in place when a re-run produces a
   different one; replace it and invalidate downstream.

Faster-Whisper's optional internal VAD stays off by default because module 02
already chose the speech spans. Turning it on filters the full WAV before
decoding; it does not change the pipeline's pre-slicing rule.

## Why full audio

Slicing audio into VAD intervals produces per-slice timestamps that must be
remapped. One rounding error per slice accumulates. On a 60-minute recording this
is exactly the failure AC-02 guards against. Transcribing the whole file keeps one
origin.

## Failure modes

| Failure | Behaviour |
| --- | --- |
| Package missing | Fail with the extra and whisper.cpp fallback hint |
| Model directory missing | Fail with the expected path and approximate size |
| CUDA requested but unavailable | Fail; do not silently fall back |
| Empty transcript | Fail; do not produce an empty edit |
| Faster-Whisper word timestamps missing | Fail; do not fabricate them |
| Transcript schema invalid | Fail before persisting |

`auto` is the exception: a missing package or model is a reason to select
whisper.cpp, not a run failure. The selected engine and transcript source are
reported in `run.json`.

## Cache

When cache-backed module runs land, the model artifact digest will be part of
the transcribe hash. `small` and `medium` must never share an entry. A prompt
version does not affect transcription.

## Tests

| Id | Case |
| --- | --- |
| T-03-01 | Fake engine returns known word times; conversion is exact |
| T-03-02 | Word ends are ceiled, starts floored |
| T-03-03 | Sentence ids are unique and stable |
| T-03-04 | Full-WAV call, not per-interval |
| T-03-05 | CPU defaults are enforced in config |
| T-03-06 | Missing word timestamps fails |
| T-03-07 | A model change invalidates downstream hashes (cache pass) |

Also covered: local model discovery, explicit missing-model errors, empty
transcripts, 16 kHz validation, CUDA load failures, and automatic
Faster-Whisper/whisper.cpp selection.

AC: 02, 03, 05, 08.
