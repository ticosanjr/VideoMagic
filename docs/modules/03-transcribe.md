# Module 03 — Transcription

## Implementation status

Implemented: SRT import and an OpenAI-compatible `/audio/transcriptions` client
with verbose JSON segments and optional word timings. Not implemented: a local
Faster-Whisper/CTranslate2 adapter and model management.

## Purpose

Produce a sentence and word transcript with source-sample timestamps that do not
drift over an hour.

## Inputs

- `work/source.wav`, the full WAV.
- `TranscribeConfig`.

## Outputs

- `state.transcript`: sentences with ids, sample spans, text, and words.
- Word probabilities for the inspector and for low-confidence warnings.

## Configuration

| Key | Default | Meaning |
| --- | --- | --- |
| `model_size` | `small` | tiny/base/small/medium/large-v3 |
| `language` | `pt` | pt/it/en/es/auto |
| `device` | `cpu` | cpu/cuda |
| `compute_type` | `int8` | int8/float16/float32 |
| `vad_filter` | `false` | Keep off when module 02 is enabled |

CPU is the default. `large-v3` is available, and the quality preset selects it,
but the operator is warned about CPU time. CUDA and float16 are opt-in.

## Algorithm

1. Load Faster-Whisper with the selected model, device, and compute type.
2. Transcribe the full WAV. Do not pre-slice by VAD intervals.
3. Ask for word timestamps. If the engine cannot produce them, fail; the
   inspector and captions depend on them.
4. Convert word times to source samples with `Fraction`, then `floor` for starts
   and `ceil` for ends.
5. Group words into sentences. Sentence ids are sequential integers starting at
   zero and are stable for a given transcript.
6. Leave text exactly as recognised, including punctuation. The UI and prompts do
   the normalisation.
7. Persist. Never mutate an existing transcript in place when a re-run produces a
   different one; replace it and invalidate downstream.

## Why full audio

Slicing audio into VAD intervals produces per-slice timestamps that must be
remapped. One rounding error per slice accumulates. On a 60-minute recording this
is exactly the failure AC-02 guards against. Transcribing the whole file keeps one
origin.

## Failure modes

| Failure | Behaviour |
| --- | --- |
| Model download unavailable | Fail with the expected path and size |
| CUDA requested but unavailable | Fail; do not silently fall back |
| Empty transcript | Fail; do not produce an empty edit |
| Word timestamps missing | Fail; do not fabricate them |
| Transcript schema invalid | Fail before persisting |

## Cache

The model artifact digest is part of the hash. `small` and `medium` never share
an entry. A prompt version does not affect transcription.

## Tests

| Id | Case |
| --- | --- |
| T-03-01 | Fake engine returns known word times; conversion is exact |
| T-03-02 | Word ends are ceiled, starts floored |
| T-03-03 | Sentence ids are unique and stable |
| T-03-04 | Full-WAV call, not per-interval |
| T-03-05 | CPU defaults are enforced in config |
| T-03-06 | Missing word timestamps fails |
| T-03-07 | A model change invalidates downstream hashes |

AC: 02, 03, 05, 08.
