# Pipeline

## 1. Contract

A module is a function over project state plus its configuration. It reads only
its declared inputs, writes only its declared outputs, and never mutates the
source media.

```python
class RackModule:
    id: str
    version: str
    requires: tuple[str, ...]
    def config_model(self) -> type[BaseModel]: ...
    def fingerprint(...) -> str: ...
    def execute(context) -> object: ...
```

`fingerprint` and the cache rules are implemented in the scaffold. `execute` is
not, for every module. Each module specification in `docs/modules/` defines what
`execute` must do.

## 2. Order and dependencies

Fixed order:

```
ingest → vad → transcribe → retakes → jl_cuts → zooms → shorts → export
```

Dependencies used by planning:

| Module | Requires |
| --- | --- |
| ingest | none |
| vad | ingest |
| transcribe | ingest |
| retakes | transcribe |
| jl_cuts | vad, retakes |
| zooms | jl_cuts |
| shorts | transcribe, retakes |
| export | all previous |

The runner executes in the fixed order. It does not topologically sort a free
graph, because the product is a rack, not a workflow builder.

## 3. Run modes

### Full run

1. Read the cache status for each enabled module.
2. Skip `cached` and `bypassed`.
3. Execute the rest in order.
4. Emit progress and persist after each module.

### Single module

- If the target is bypassed or disabled: `ModuleBypassedError`.
- If any earlier enabled, non-bypassed module is `dirty`, `missing`, `failed`,
  or `blocked`: `UpstreamDirtyError` with only those ancestors.
- With `run_upstream=true`, add the dirty ancestors to the plan, skipping any
  cached ones.
- If the target is cached and no ancestor needs work: return an empty plan.
- `RUNNING` anywhere means another job owns the project.

The implementation is `domain/planning.py`; the tests are
`tests/unit/test_planning.py`.

## 4. Module outputs

| Module | Output | Persisted in |
| --- | --- | --- |
| ingest | `MediaInfo`, PCM, optional proxy, PCM digest | state + `work/` |
| vad | speech sample spans | `state.vad_intervals` |
| transcribe | sentences and word timings | `state.transcript` |
| retakes | culls and restores | `state.retake_culls`, `retake_guard_restores` |
| jl_cuts | video and audio segments | `state.video_segments`, `audio_segments` |
| zooms | transforms on existing segments | `state.video_segments[*].transform` |
| shorts | vertical source windows and artifacts | `state.vertical_clips` + `exports/` |
| export | FCPXML, xmeml, Kdenlive MLT, optional MP4 | `exports/` |

## 5. Failure semantics

- A module either completes or raises. There is no "partially succeeded" state.
- Artifacts are written to a temporary directory, then renamed into the cache.
- State is written only after the artifacts land.
- A failure leaves the previous cache entry usable.
- The job records the failing module and a message; the UI shows `failed`.
- Re-running resumes from the first module whose hash differs.

## 6. Cancellation

- Checked between modules.
- Checked inside the FFmpeg and Whisper subprocess supervisor.
- A cancelled job does not promote its partial artifacts.
- The lock is released in `finally`.

## 7. Progress

Events:

```
job_started
module_started {module, cached}
module_progress {module, percent, message}
module_done {module, duration_ms}
module_failed {module, code, message}
job_done {status}
```

Percent is per module, not a fake global ETA. A global bar weights modules by the
measured cost of their own media, so it can be honest without pretending to know
the future.

## 8. The retake step in detail

1. Split the transcript into overlapping windows of
   `context_window_sentences` sentences.
2. Send indexed text. The prompt states that the payload is data.
3. Parse the strict JSON response.
4. Reject unknown ids.
5. Detect repetition clusters: exact normalized repeats initially; the model is
   asked to flag non-exact ones in its reasoning.
6. Apply `keep_last` or `keep_best`.
7. Merge window decisions. If a sentence appears in two windows, a discard needs
   both windows to agree or an explicit manual override.
8. Persist culls and restorations.

## 9. The cut step in detail

1. Sort kept sentences by source time.
2. Convert each padded speech interval to covering frames.
3. Add handles from the source.
4. Create one video segment and one audio segment per accepted clip.
5. Offset audio for a J-cut when the handle allows it.
6. Add a logarithmic micro-fade at each join.
7. Pack timeline positions contiguously from frame zero and sample zero.
8. Validate packing and overlaps.

## 10. Vertical shorts in detail

1. The model proposes source-time windows bounded by sentence edges.
2. Each window is intersected with the kept source ranges.
3. The conformed duration is checked against the configured minimum and maximum.
4. A clip below the minimum is dropped and reported. It is never padded with
   discarded takes.
5. The crop is `center_crop_9_16` with `crop_focus_x`.
6. Subtitles are rendered from word timings.
7. The export format decides between timeline clips and MP4 files.

## 11. Portable pipeline path

`application/portable.py` implements the complete single-file path:

```
FFprobe → PCM at media rate → Silero (16 kHz) or FFmpeg VAD → optional SRT/ASR
        → Faster-Whisper or whisper.cpp → retake culling → pads → timeline
        → three exports
```

`videoflow run` and `videoflow demo` call it. `auto` uses Silero when the pinned
model and ONNX Runtime are present and falls back to FFmpeg `silencedetect`
otherwise. Pads are applied after retake culling so a discarded take cannot
survive as pad-only audio. The path supports local Faster-Whisper, whisper.cpp
as the automatic fallback, SRT/ASR transcripts, LLM retakes, shorts, and all
three exporters.

## 12. Implementation order

Done:

1. Ingest and PCM fingerprint
2. Timeline, J/L-cuts, zoom metadata
3. FCPXML, xmeml, and Kdenlive MLT with structural contract tests; OTIO remains a helper
4. Portable FFmpeg VAD and onefile executable
5. In-process jobs, REST/SSE, and live MCP job tools
6. SRT transcript import, LLM retakes, and the keeper guard
7. Vertical shorts: selection, culling, captions, and 1080x1920 render
8. Per-stage telemetry, bounded logs, and the telemetry rack UI
9. SRT/ASR transcripts, manual overrides, and Shorts in jobs
10. Persistent projects, atomic revisions, transcript routes, and operator
    presets
11. Silero VAD, source-rate rescaling, pads, and ONNX packaging
12. Faster-Whisper, full-WAV word timestamps, local model management, and
    portable model packaging

Next, in order:

13. Cache-backed per-block runs and the full rack inspector
14. NLE audio transitions, keyframed zooms, subtitles, MP4
15. Three-app import spike and long-file QA

Each pass removes the `xfail` marker for its contracts and adds the media
integration tests described in [testing.md](testing.md).
