# VideoFlow 0.22.2

This release fixes the "already running" trap caused by an old VideoFlow
service. A 0.20.0 process from a previous session was still listening on
`127.0.0.1:8765`; every newer AppImage detected it, opened the old UI, and
exited. That is why the file browser kept failing and the page looked offline.

## Fixed

- **Version-aware startup.** The launcher reads `/health`, compares the running
  version with its own, and no longer reuses an older service. It stops the old
  VideoFlow process tree, waits for the port to become free, and starts the
  current version.
- **Stale process discovery.** VideoFlow `serve`/`mcp`/`desktop` processes are
  discovered through `/proc`, including AppImage-mounted binaries and their
  parent processes, even when the old version had no PID file.
- **Current launcher protection.** Cleanup never kills the AppImage launcher
  that owns the service serving the UI.
- **Port-first cleanup.** Processes that own a listening port are stopped before
  launchers and parents. SIGKILL is the fallback when SIGTERM does not finish.
- **Services tab.** One screen now shows:
  - current PID, port, version, and URL;
  - all other VideoFlow services;
  - Stop for one service;
  - Stop all others;
  - Restart current and Stop current;
  - the server log tail and log path.
- **Server log.** Startup, version replacement, cleanup, stop, restart, and
  crashes are written to `videoflow-data/logs/server.log`.
- **Connection retry.** The UI now shows "Connecting…" and retries instead of
  permanently displaying "offline" when the browser opens before the server is
  ready.
- **`videoflow cleanup`** stops other VideoFlow services from the terminal.
- `videoflow status` lists discovered services, not only the PID file.

## If you have an old process

The new AppImage should remove it automatically. You can also run:

```bash
./VideoFlow-0.22.2-x86_64.AppImage serve --open
```

If you need to clean manually before starting:

```bash
pkill -f 'videoflow.*serve'
```

Or after starting 0.22.2, open the **Services** tab and choose
**Stop all others**.

## Artifacts

- `videoflow-0.22.2-linux-x86_64` — SHA-256 `d751925ab12b8af96f0929f238fab1f7ce4fc142255e0e1be2231816436edf3e`
- `VideoFlow-0.22.2-x86_64.AppImage` — SHA-256 `f8d2982cc915e847765962f8221efbf2dd3e45be58a4f4a08e2589b1f50a10aa`

## Run

```bash
chmod +x VideoFlow-0.22.2-x86_64.AppImage
./VideoFlow-0.22.2-x86_64.AppImage serve --open
```

Then use the **Services** tab, or:

```bash
videoflow status
videoflow restart
videoflow cleanup
videoflow stop
```

The build remains lean: speech models are downloaded from the Models tab on
first use. Windows PE is not included because the Windows/Wine build host was
unavailable.
