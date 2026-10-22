# VideoFlow 0.25.0

This release closes the main gap in the recipe engine: steps are now individually
runnable and resumable, not just nodes in a full-recipe run.

## Per-step checkpoints

Every successful step writes:

```text
<output>/work/steps/<step_id>/
  manifest.json
  snapshot.json
```

The fingerprint covers:

- step type and version;
- validated parameters;
- source fingerprint;
- upstream step hashes.

On the next run in the same output directory, matching steps are reused. Steps
that produce files verify that their outputs still exist; deleting an export or
a rendered Short reruns only the affected step. Changing a step parameter
invalidates that step and its dependents.

`run.json` and job results expose `step_runs`:

```json
{
  "id": "vad",
  "type": "audio.vad",
  "status": "cached",
  "elapsed_ms": 0,
  "fingerprint": "...",
  "outputs": []
}
```

## Step-scoped execution

```bash
videoflow recipe step recipes/viral_shorts_batch.json shorts /media/source.mp4 -o /media/out
videoflow recipe run recipes/viral_shorts_batch.json /media/source.mp4 -o /media/out --force
```

- `POST /api/v1/steps/{step_id}/run` runs the target and its dependency closure.
- `POST /api/v1/recipes/run` accepts `through` and `resume`.
- MCP adds `videoflow_run_step`.
- `--force` ignores existing checkpoints.
- The Config modal has a **Reuse existing step checkpoints** switch.

## Visual editor

- Nodes show **cached**, **executed**, **running**, or **failed**.
- The job panel shows cached/executed counts.
- The step inspector has **Run to here**, which runs only that node and its
  dependencies.
- The full-width canvas, collapsible inspector, add-step popover, and JSON/config
  modals from 0.24.0 are unchanged.

## Dependency validation

Recipes are rejected when a step's declared upstream types are missing. This
prevents a partial run from subtracting retake culls from empty speech or
selecting Shorts without a transcript.

- `retakes.cull` now requires `audio.vad` and `transcribe`.
- Built-in Shorts recipes put NLE export after Shorts rendering.
- `audio.vad` and local/HTTP transcription still use the cross-output analysis
  cache in `<videoflow-home>/cache/recipe-v1/`.

## Validation

- 401 Python tests passed; 14 UI tests passed; enforced coverage 98.72%.
- The 0.25.0 AppImage started without a terminal.
- A step-scoped run through `vad` produced only `ingest` and `vad`.
- A full run after that reused `ingest` and `vad`.
- A second full run reused all ten steps.
- Opening the AppImage again reused the running service.
- Playwright verified the node badges and **Run to here**.

## Artifacts

- `videoflow-0.25.0-linux-x86_64` — SHA-256 `8b8085acd961ad0cb94222592df8aea9474c3e98b120d086d7ec7b94e4a044c7`
- `VideoFlow-0.25.0-x86_64.AppImage` — SHA-256 `ad260ea2598ac1bd93141b88cc7d816b94045319f9a83446cde96adca0089fd4`

The build is lean; speech weights are downloaded from the Models tab. Windows
PE is not included because no Windows/Wine build host was available.
