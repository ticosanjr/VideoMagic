# Developer manual

## 1. Setup

```bash
uv sync --extra dev --extra faster-whisper
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Python 3.11+. `src/` layout. Tests import through `pythonpath = ["src"]`.

## 2. Current state

Implemented:

- rational time and frame coverage
- project state and JSON Schemas
- cache canonicalization and module hashing
- planning and upstream rules
- retake guard and exact clustering
- path jail, redaction, timeline checks
- preset loading
- FFprobe ingest, PCM extraction, and media fingerprint
- deterministic timeline builder with J/L-cuts, handles, fades, and punch-ins
- FCPXML 1.9/1.10, xmeml, and OTIO exporters plus `export_timeline`
- Silero VAD with FFmpeg fallback and the portable pipeline service
- local Faster-Whisper/CTranslate2 transcription with word timestamps, a pinned
  bundled model, and whisper.cpp fallback
- SRT import, OpenAI-compatible retake culling, and the keeper guard
- unified CLI (`run`, `serve`, `mcp`, `doctor`, `demo`, `version`)
- PyInstaller onefile packaging for Linux and Windows, plus a Linux AppImage
- MCP tool registration and structured not-implemented responses
- health endpoint, UI mount, and MCP mount
- allowlisted filesystem browsing, folder creation, and media probing for the
  rack path picker
- unit, contract, and real-FFmpeg media tests

Stubbed, with `xfail` contracts:

- per-module `execute` methods and per-module reruns
- NLE audio transitions, keyframed progressive zooms, and direct MP4 rendering

## 3. Layout

```
src/videoflow/
  domain/        pure rules; no I/O
  application/   cache, runner, jobs, ports
  modules/       eight module classes and fingerprints
  adapters/      ffmpeg, silero, faster_whisper, whisper, asr, llm
  exporters/     fcpxml, xmeml, otio, mp4
  api/           FastAPI, CLI
  mcp_server/    registry, SDK server, CLI
  presets/       shipped JSON
schemas/         generated, committed
tests/unit/      fast, pure
tests/contract/  public surface
ui/              SvelteKit + Tailwind
```

## 4. Adding a module capability

Ingest is the reference implementation: `adapters/ffmpeg.py` does the work,
`application/timeline_builder.py` consumes its output for the cut stage, and
`application/export_service.py` writes the artifacts. The module class still has a
stub `execute`; wire it to these services in the job pass.

For a new model adapter or transcription path:

1. Implement the adapter behind the existing protocol with a lazy import. The
   import must not be required for the unit suite.
2. Implement `Module.execute` to call the adapter, validate the output, and
   persist through the service.
3. Write artifacts to a temp directory, then promote.
4. Remove the module's `xfail` in `tests/contract/test_pipeline.py`.
5. Add the unit tests from the module spec.
6. Add a `media` test with a generated fixture.
7. Run mypy and ruff.

Do not import FFmpeg, ONNX, CTranslate2, or HTTP types into `domain/`.

## 5. Adding a tool

1. Add a `ToolSpec` to `registry.py`.
2. Register a decorated function in `server.py` with typed parameters and a
   docstring. The SDK derives the schema from the signature.
3. Call an application service. No edit logic in the wrapper.
4. Return a dict. Errors use `to_dict()`.
5. Update the tool table in `docs/mcp.md`.
6. Add a contract test that the registry and `list_tools()` agree.

The historical name `videoflow_export_fcpxml` is kept. Do not rename it without a
compatibility period; agents may already call it.

## 6. Changing an exporter artifact

The three timeline writers already share `exporters/common.py` and
`application/export_service.py`.

1. Build from the shared timeline view; never re-run analysis.
2. Keep the preflight in `common.py` authoritative.
3. Use rational formatting from `domain/timebase.py`.
4. Parse the output back in a test.
5. Add a golden file under `tests/fixtures/`.
6. Add or update the manual import step in `docs/manuals/nle-import.md`.

Audio transitions and keyframed progressive zooms are the next exporter slice.
Do not add a guessed attribute without the three-app import spike.

## 7. Changing a schema

1. Change the Pydantic model.
2. Run `uv run python scripts/export_schemas.py`.
3. Commit the schema and the model together.
4. If the change is breaking, bump `SCHEMA_VERSION` and add a migration.
5. Update `docs/data-model.md` and any preset.
6. `test_schemas.py` enforces the commit.

## 8. Cache rules

Never add mtime, a random id, or a wall-clock timestamp to a module hash. Never
remove `upstream_hash`, `media_fingerprint`, or `model_artifact_digest`. A module
that ignores an input must still declare it, or the cache will lie.

A float in a hash payload is quantized. If a new parameter needs finer precision,
change the canonicalizer deliberately and invalidate the cache version.

## 9. Error handling

- Raise a `VideoFlowError` subclass. Do not return `None` to mean failure.
- Add a code, an HTTP status, and a doc row.
- Include actionable context: module, path, ancestor list.
- Never include a secret.
- Log at the boundary, not in the domain.

## 10. Tests

| Layer | What to fake |
| --- | --- |
| domain | nothing |
| application | adapters |
| adapters unit | the native binary/library |
| adapters media | real FFmpeg on a generated fixture |
| exporters | a fixed state and a golden file |
| API | TestClient |
| MCP | the SDK's in-process `list_tools`/`call_tool` |

Keep unit tests under a second. Mark anything longer.

## 11. UI

```bash
cd ui
npm install
npm run dev
npm run check
npm run build
```

The scaffold is static. When wiring it, generate a typed client from the JSON
Schemas; do not hand-write interfaces that drift.

## 12. Portable build

```bash
cd ui && npm ci && npm run build && cd ..
uv sync --extra dev
uv run python scripts/build_portable.py --fetch-ffmpeg
./dist/videoflow doctor
./dist/videoflow demo -o /tmp/videoflow-demo
```

The spec is `packaging/videoflow.spec`. It bundles presets, the UI, and the
`vendor/` FFmpeg binaries. `find_binary` resolves the bundle first. Add a new
lazily imported package to `hiddenimports` or the frozen binary will fail with
`ModuleNotFoundError`. Rebuild after touching the CLI, API mount, or MCP server.

Windows must be built with a Windows Python and PyInstaller. The release on this
machine used Wine WoW64 plus the Python embeddable distribution; the resulting
PE32+ executable was smoke-tested under Wine. GitHub Actions is not used.

## 13. Release

1. All tests, ruff, and mypy green.
2. Media suite on a generated fixture.
3. Manual NLE script in `docs/testing.md`.
4. `CHANGELOG.md` updated.
5. Version bumped in `pyproject.toml` and `src/videoflow/__init__.py`.
6. Tag. There is no license yet; resolve that before a public release.

## 13. Definition of done

- The contract test exists and is not xfail.
- The failure cases from the module spec are covered.
- The docs match the signatures.
- Secrets are out of state and logs.
- A full run on the fixture succeeds.
- The manual step, if any, is written down.
