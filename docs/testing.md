# Test plan

## 1. Principle

The suite must be green and honest at the same time. A scaffold full of failing
tests trains people to ignore red. A suite that skips the unimplemented surface
hides the contract. VideoFlow resolves this with two layers:

- **Passing tests** for everything the repository claims to do now.
- **Expected failures** (`xfail(strict=True)`) for specified but unbuilt
  behavior. A stale xfail (the feature landed and the test passed) fails the
  suite, so the marker cannot rot.

## 2. Gates

| Scope | Line coverage | Notes |
| --- | --- | --- |
| `videoflow.domain`, `application.cache`, `application.timeline_builder` | **95%** now | Current: 98.32% (448 passing, 10 strict xfail, 8 deselected) |
| Domain, runner, cache, exporters | 90% when engines land | Exporters require golden files |
| Adapters | 80% with fakes | Native libraries are faked in unit tests |
| UI | `npm run check`, `npm test`, `npm run test:e2e`, `npm run build` | Playwright: graph, inspector, schema fields, split-screen source, palette, NLE validation, run history |

A stub is excluded from coverage only when it is listed in
`[tool.coverage.run].omit`. `# pragma: no cover` is reserved for platform-only
fallbacks and must be justified in review.

## 3. Commands

```bash
uv run pytest                           # unit + contract, coverage gate
uv run pytest -q -m "not xfail"         # only implemented behavior
uv run pytest -m media --no-cov         # real FFmpeg fixtures (also in CI)
uv run pytest -m slow --no-cov          # performance checks
uv run pytest -m manual --no-cov        # prints the manual checklist
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python scripts/build_portable.py --fetch-ffmpeg  # packaging smoke
```

The default run excludes `media`, `slow`, and `manual`. Use `--no-cov` for a
subset run so the global coverage gate does not fail on modules that were not
imported. GitHub Actions runs Linux lint, Python, media, UI, and Playwright checks. Playwright runs with
`cd ui && npm run test:e2e`; its JSON report lands in
`ui/test-results/results.json`.

## 4. Markers

| Marker | Meaning |
| --- | --- |
| `contract` | Public surface that is specified; starts as xfail |
| `media` | Needs FFmpeg and generated media |
| `slow` | Long media, timing, or model inference |
| `manual` | A human must import or listen |

## 5. Current test map

### Unit (passing)

| File | Covers |
| --- | --- |
| `test_timebase.py` | Rational conversion, pads, frame coverage, 60-minute proof, Hypothesis round-trips |
| `test_cache.py` | Canonical form, key order, float quantization, identity inputs, no mtime |
| `test_state.py` | Schema rules, forbidden extra fields, CPU defaults, rational fields |
| `test_retakes.py` | Cluster detection, keep-last restoration, keep-best, unknown ids |
| `test_planning.py` | Full run, single module, dirty ancestors, bypass, running job |
| `test_paths.py` | Allowlist, symlink escape, `..` escape |
| `test_redact.py` | Secret replacement |
| `test_timeline.py` | Overlaps, packing, inverted spans |
| `test_presets.py` | Shipped presets and validation |
| `test_errors.py` | Error codes and payloads |
| `test_timeline_builder.py` | Span merge, frame coverage, J/L shifts, handles, zooms, pan |
| `test_ffmpeg_adapter.py` | Probe parsing, PCM extraction, digest, FFmpeg failures |
| `test_silence.py` | `silencedetect` parsing, complement, blip filtering |
| `test_silero.py` | ONNX windows, thresholding, gap merge, minimum speech, WAV validation |
| `test_vad_engine.py` | Engine auto/fallback, 16 kHz rescaling, pads, explicit failure |
| `test_transcript.py` | SRT parsing, BOM/CRLF, malformed files |
| `test_llm.py` | OpenAI-compatible JSON transport, retry, errors, redaction |
| `test_asr.py` | Verbose JSON transcription, timestamps, errors, redaction |
| `test_faster_whisper.py` | Full-WAV calls, word timestamps, exact floor/ceil samples, model errors, CUDA failure |
| `test_retake_service.py` | Windows, ids, exact fallback, guard, subtraction |
| `test_shorts.py` | Heuristic/LLM windows, prompt/reprompt, auto hook, virality, filler cuts, censor, keyword/emoji/brand styling, culls, karaoke ASS, proportional fallback, events, source trimming |
| `test_metadata.py` | Platform limits, hashtags, tone, title fallback, invalid inputs |
| `test_fonts.py` | TTF family parsing, asset round-trip, invalid uploads |
| `test_audio.py` | Opt-in high-pass, denoise, loudnorm filter chains |
| `test_images.py` | PNG asset round-trip and invalid image rejection |
| `test_music.py` | Mix filter, ducking, fades, and music asset store |
| `test_tts.py` | OpenAI-compatible speech synthesis request and audio write |
| `test_dubbing.py` | Translation prompt and response validation |
| `test_brand_templates.py` | Template round-trip, apply, and delete |
| `test_tracking.py` | Motion centroid, static fallback, empty frames |
| `test_audio_analysis.py` | Loud-region peaks and silence fallback |
| `test_video_analysis.py` | Scene-time parsing, deduplication, and sample windows |
| `test_url_import.py` | yt-dlp command, missing binary, non-http URL rejection |
| `test_publishing.py` | Webhook dispatch and queue cancellation |
| `test_multimodal.py` | Audio-feature labels and motion-region centroids |
| `test_project_templates.py` | Template round-trip, sanitization, config import/export |
| `test_portable.py` | End-to-end portable service with a fake engine and retakes |
| `test_jobs.py` | Job completion, failure, cancellation, queue limit, pruning, VAD/Faster-Whisper, detailed zoom/fade/Shorts/caption forwarding |
| `test_telemetry.py` | Stage lifecycle, durations, logs, filters, cap |
| `test_cli.py` | `version`, `doctor`, `run` dispatch, VAD/Faster-Whisper, Shorts and zoom/fade options, usage |
| `test_release.py` | Release retention keeps the newest three folders and rejects invalid limits |
| `test_capabilities.py` | External-provider policy, localhost exception, global kill switch, capability manifest |
| `test_runtime.py` | Portable home, binary/model discovery including Faster-Whisper, UI discovery, allowed roots |

### Contract (passing now)

| File | Covers |
| --- | --- |
| `test_exporters.py` | FCPXML 1.9/1.10 media-rep and audio fades, xmeml v4 full files/links and transitions, native Kdenlive MLT and volume fades, export service, preflight failures |
| `test_ingest_media.py` | Real FFprobe, PCM extraction, and silence detection (`media`) |
| `test_shorts_media.py` | Renders two 1080x1920 clips with ASS via the CLI (`media`) |
| `test_api_jobs.py` | Job create/poll, stages/logs, new options, path jail, SSE, system, per-Short edit/metadata/thumbnail, real media (`media`) |
| `test_api_fs.py` | Filesystem roots/listing/filtering, hidden files, truncation, symlink escapes, directory creation, media probe |
| UI `format.test.ts` | Duration, bytes, elapsed time, date, status text (Vitest) |
| UI `paths.test.ts` | POSIX and Windows basename, parent, and output suggestion |
| `test_mcp.py` | Twelve tool names, typed errors, preset/state resources |
| `test_mcp_live.py` | Live VAD, Faster-Whisper/whisper.cpp transcription, transcript, staged edits, shorts, job polling, export, resources |
| `test_api.py` | `/health` and MCP redirect |
| `test_schemas.py` | Committed schemas match models, no `api_key` |
| `test_pipeline.py` | Missing-source ingest and missing-audio transcription failures |

### Contract (xfail until implemented)

| File | Contract |
| --- | --- |
| `test_exporters.py` | Audio fades in all three dialects (AC-01); direct MP4 render |
| `test_pipeline.py` | Per-module `execute` methods and the rack runner |

## 6. Acceptance coverage

| Criterion | Automated proof | Manual proof |
| --- | --- | --- |
| AC-01 no click | Fade structures are tested in FCPXML, xmeml, and Kdenlive; manual import remains xfail | Listen at three joins per NLE |
| AC-02 lip sync | Every video edge is a frame index; builder tests cover frame coverage; 60-minute rational proof | Spot-check a long import |
| AC-03 last take | Fake LLM drops the final take; guard restores it | Inspector shows a restoration |
| AC-04 agent autonomy | Scripted MCP session produces three timelines and three shorts | None |
| AC-05 partial cache | Hash of 01–05 unchanged; plan is 06+08 | One timed real-file run |
| AC-06 NLE import | Three artifacts are written and parsed; preflight rejects invalid timelines | Import in Resolve, Premiere, Kdenlive |
| AC-07 secret hygiene | Schema sweep, redaction, resource snapshot | None |
| AC-08 CPU default | Config assertions | None |
| AC-09 atomic failure | Failed module keeps the previous cache entry | None |
| AC-10 English | String review | Short manual pass |

## 7. Media fixtures

Do not commit copyrighted media.

```bash
mkdir -p tests/fixtures/generated
ffmpeg -f lavfi -i testsrc2=size=1280x720:rate=30 \
       -f lavfi -i "sine=frequency=440:sample_rate=48000" \
       -t 60 -c:v libx264 -pix_fmt yuv420p -c:a aac \
       tests/fixtures/generated/sample.mp4
```

For speech-shaped audio, gate a tone with `volume=enable='between(t,...)'` so VAD
sees speech and silence without a real voice. A 65-minute fixture is generated
only in the `slow` job.

Golden files:

```
tests/fixtures/fcpxml/straight-cut.fcpxml
tests/fixtures/fcpxml/jcut.fcpxml
tests/fixtures/fcpxml/punch-in.fcpxml
tests/fixtures/xmeml/straight-cut.xml
tests/fixtures/kdenlive/straight-cut.kdenlive
```

The three timeline shapes are the compatibility spike. Freeze the dialect only
after all three open in their target app.

## 8. Unit test rules

- No network in unit tests.
- No model download.
- No real FFmpeg unless marked `media`.
- A fake LLM is a fixture that returns a chosen payload, including illegal ones.
- Use `tmp_path`; never write into the repository.
- Hypothesis examples are bounded so the suite stays under ten seconds.

## 9. Failure-case catalog

Every module spec lists these under **Failures**. The suite must cover:

- Inverted or empty spans.
- Pads that collapse against media bounds.
- Unknown retake ids.
- A model that discards the keeper.
- Dirty upstream on a single-module run.
- A second job on a running project.
- Path escapes, including symlinks.
- Missing media.
- Export with an offline source.
- An export with zero valid clips.
- A shorts window below the minimum after conform.
- A JSON schema drift.

## 10. Performance checks

| Check | Budget | Marker |
| --- | --- | --- |
| Zoom-only rerun after a cached analysis | < 1 s on the fixture, excluding export I/O | `slow` |
| Cache canonicalization | < 1 ms per module | unit |
| Frame/sample conversion | < 10 µs per call | unit |
| 60-minute transcript drift | 0 accumulated frames | `slow` |

The one-second figure is a product target, not a CI wall-clock assertion on a
loaded machine. The plan assertion is the hard gate; timing is advisory and
recorded.

## 11. Manual release script

Run before tagging a release:

1. Import `tests/fixtures/fcpxml/*.fcpxml` into Resolve. Confirm the timeline,
   detached audio, and transforms.
2. Import `tests/fixtures/xmeml/*.xml` into Premiere. Confirm tracks, audio
   offset, and motion.
3. Import `tests/fixtures/kdenlive/*.kdenlive` into Kdenlive 23.04+. Confirm the
   V1/A1 tracks, timeline duration, and no missing clips.
4. Listen to every join at high volume with headphones.
5. Run a 60-minute talking head. Scrub the last ten minutes for drift.
6. Disable zooms. Rerun. Confirm only export executed.
7. Kill the API during transcription. Restart. Confirm the previous cache is
   intact and the job is not stuck `running`.
8. Switch the UI to English only. Search the build output for Portuguese
   strings.
9. Stage with `scripts/release.py --require-all --keep 3`, confirm only three
   release folders remain, and remove `build/`, `dist/`, coverage files, and
   generated caches.

Record the result in the release notes, not in a chat.

## 12. Adding a test

1. Write the contract first, marked `xfail(strict=True)` with the AC id.
2. Implement the smallest slice that passes.
3. Remove the marker in the same change.
4. Add the failure cases from the module spec.
5. Keep the coverage gate above 95% for pure code.

A contract without an implementation is allowed. An implementation without a
contract is not.
