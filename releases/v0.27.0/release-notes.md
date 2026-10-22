# VideoFlow 0.27.0

This release adds run comparison to the recipe workspace.

## Run comparison

After a successful recipe run, the UI finds the previous successful job for the
same output and recipe and offers **Compare**.

The modal shows:

- current versus previous duration;
- cached and executed step counts;
- warning counts;
- a per-step table with previous/current status and elapsed milliseconds.

The comparison uses the normal in-memory job history; no new database or
persistent store is required.

## Validation

- 405 Python tests passed; 14 UI tests passed.
- Playwright ran the same recipe twice, confirmed the previous-run summary, and
  opened the comparison modal with six step rows.
- The 0.27.0 AppImage started without a terminal and served the comparison UI.
- Opening the AppImage again reused the running service.

## Not in this release

Keyframed progressive zooms and video transitions remain the next creative
editing pass. This release focuses on run observability.

## Artifacts

- `videoflow-0.27.0-linux-x86_64` — SHA-256 `b362509d26f7d29d3f832ec6cc3a2da98d67507beffed6453643fe575b710e21`
- `VideoFlow-0.27.0-x86_64.AppImage` — SHA-256 `ac6d1ea667d7a81172be9c2e0c5fae7eedd4e238fd3f7bd11c7ba92119672af5`

The build is lean; speech weights are downloaded from the Models tab. Windows
PE is not included because no Windows/Wine build host was available.
