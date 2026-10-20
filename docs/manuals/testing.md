# Testing manual

This is the hands-on companion to [testing.md](../testing.md). Use it for a local
run and for the release gate.

## 1. Fast loop

```bash
uv run pytest -q
uv run pytest -q -m "not xfail"
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Expected for the current suite:

```
301 passed, 11 xfailed, 7 deselected
coverage 99.27%
UI: 8 passed (Vitest)
```

`xfail` is part of the design. A strict xfail that starts passing fails the suite,
which means the marker is stale and must be removed.

## 2. One test

```bash
uv run pytest tests/unit/test_timebase.py -q
uv run pytest tests/unit/test_planning.py::test_dirty_upstream_blocks_a_single_module_run -q
```

## 3. Generated media

```bash
mkdir -p tests/fixtures/generated
ffmpeg -f lavfi -i testsrc2=size=1280x720:rate=30 \
       -f lavfi -i "sine=frequency=440:sample_rate=48000" \
       -t 60 -c:v libx264 -pix_fmt yuv420p -c:a aac \
       tests/fixtures/generated/sample.mp4
```

Speech-shaped fixture: gate the tone with silence so VAD has something to find.
Do not commit real recordings.

## 4. Media tests

```bash
uv run pytest -m media -q --no-cov
```

Real FFmpeg probe and PCM extraction on a generated fixture. No model download.
Use `--no-cov` for subset runs so the global coverage gate is not evaluated
against unimported modules.

## 5. Slow tests

```bash
uv run pytest -m slow -q --no-cov
```

These cover the zoom-only cache timing and the 60-minute drift. They are advisory
on a loaded CI machine. The plan assertion is the hard gate.

## 6. UI checks

```bash
cd ui
npm run check
npm run test
npm run build
```

`npm run test` covers date/duration/status formatting. The rendered rack is
checked manually by starting a job and confirming per-block progress, timestamps,
status icons, the log drawer, the override inspector, and local transcription.

## 6b. Local Whisper smoke

```bash
uv run videoflow doctor                 # whisper.found must be true
uv run videoflow run speech.mp4 -o /tmp/vf-whisper --transcribe --asr-language en
uv run python - <<'PY'
import json
report = json.load(open("/tmp/vf-whisper/run.json"))
assert report["transcript_source"] == "whisper"
print(report["transcript_sentence_count"])
PY
```

The fixture must contain real speech; a tone only proves the process ran. Use
`--whisper-model path/to/ggml-small.bin` to compare quality.

## 7. MCP smoke

```bash
uv run videoflow-mcp
```

In another terminal, or from the host, list tools. With the SDK:

```bash
uv run python - <<'PY'
import asyncio
from videoflow.mcp_server.server import build_server
print(asyncio.run(build_server().list_tools()))
PY
```

Expect twelve tools. Analysis tools answer immediately; edit tools stage options
for the next pipeline run. A successful smoke should load media, run VAD,
transcribe, read the transcript, start a job, poll it to success, and export.

## 8. API smoke

```bash
uv run videoflow-api
curl -s http://127.0.0.1:8765/health
```

Expect `{"status":"ok","service":"videoflow","version":"0.19.0"}`.

## 9. AppImage contract

```bash
uv run pytest -m packaging --no-cov
```

This runs `scripts/smoke_appimage.py` against the newest staged AppImage:
`version`, `doctor`, `demo`, `APPIMAGE_EXTRACT_AND_RUN=1 version`, and a
`serve` health check. The unit suite also builds an AppDir with a fake binary
and asserts the AppRun no-argument branch, desktop entry, icon, and executable
bits.

## 10. Portable smoke

```bash
uv run python scripts/build_portable.py --fetch-ffmpeg
env -i PATH=/nonexistent ./dist/videoflow doctor
env -i PATH=/nonexistent ./dist/videoflow demo -o /tmp/videoflow-demo
env -i PATH=/nonexistent ./dist/videoflow serve --port 8799
```

Then check `/health`, `/`, `/mcp/`, and the twelve tools over `videoflow mcp`.
On Windows, run the same commands with `videoflow.exe`; FFmpeg is found inside
the bundle, so an empty `PATH` is the proof.

## 11. Release gate

Run `docs/testing.md` section 11. Record:

- all commands and results;
- coverage;
- the three NLE imports with versions;
- the long-file lip-sync check;
- the cache-timing observation;
- any accepted deviation.

A release without the manual section is not a release.

## 12. Reading a failure

1. Is it an `xfail` that now passes? Remove the marker and update the docs.
2. Is coverage below 95%? Look at the missing lines, not at the threshold.
3. Is a Pydantic schema test failing? Run `scripts/export_schemas.py` and inspect
   the diff before committing.
4. Is a path test failing on symlinks? Check the resolution order; do not relax
   the jail.
5. Is a planning test failing? Print the status map and the planned modules. The
   rule is in `domain/planning.py`.

## 13. Adding a case

- Unit: no I/O, no network, fast.
- Contract: public surface; xfail if not built.
- Media: FFmpeg fixture, marked.
- Manual: a checklist step, not an assertion.

Every bug gets a test that fails before the fix and passes after it.
