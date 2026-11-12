# Tray icon that owns the local service

Date: 2026-11-12
Status: proposed

## Intent

Make VideoFlow easier to run day to day. Today the AppImage opens a terminal
running `videoflow serve --open` and the terminal must stay open. A tray icon
should start the service, open the UI, restart it, stop it, and quit without a
terminal.

## Goals

- New `videoflow tray` command.
- The tray process owns the server lifecycle: it starts the service itself and
  stops it when the tray quits.
- Menu actions: open UI, start, stop, restart, status, quit.
- Existing `status`/`stop` CLI behavior keeps working through the PID file.
- Graceful fallback when no tray backend or display is available.
- Optional dependency, so the core install and tests do not need a GUI stack.

## Non-goals

- No release, packaging change, or new artifact in this task.
- No login autostart.
- No Windows/macOS packaging work now.
- No new web UI, no browser-tab interception.
- No second copy of the VideoFlow API inside the tray process.

## Anti-goals

- A tray that quits but leaves an orphan server.
- A tray that crashes when `pystray` or a display is missing.
- Two services fighting for the same port.
- Silent duplicate startup when a compatible service is already running.

## Constraints

- The UI is a local web app; there is no desktop shell or window to close.
- `pystray` must run its loop on the main thread on Linux and macOS.
- Uvicorn can run in a worker thread; it skips signal handlers outside the main
  thread.
- The existing service lock, PID file, health probe, and log helpers are the
  source of truth.

## Approaches

- **A — one process: tray on the main thread, Uvicorn in a worker thread.**
  Restart sets `server.should_exit`, joins, and builds a fresh app/server. Quit
  stops the server and closes the tray. Chosen.
- **B — supervisor: tray spawns `videoflow serve` as a child.** Better
  isolation, but two processes, a fragile frozen-binary spawn, and orphan risk
  when the tray is killed with `-9`.
- **C — native GTK/AppIndicator without `pystray`.** Cleaner Linux integration,
  but a system dependency per distro and a worse portable build.

A is chosen because it keeps one process, reuses the existing Uvicorn restart
shape, and packages as one executable.

## Design

### Dependency

Add an optional extra in `pyproject.toml`:

```toml
tray = ["pystray>=0.19", "pillow>=10"]
```

`uv sync --extra tray` for local use. The portable build would bundle both when
the tray is enabled; that is a later packaging task, not part of this change.

### Modules

- `src/videoflow/application/tray.py`
  - `ServerSupervisor`: owns the Uvicorn `Server` and its worker thread.
    - `start()`: resolve host/port, stop an older VideoFlow service on the port
      through `stop_services_on_port`, create the app, write the PID file, start
      the thread, log the transition.
    - `stop(timeout)`: set `should_exit`, join, remove the PID file, log.
    - `restart()`: `stop()` then `start()`.
    - `running`: health probe on the configured host/port.
    - `restart_requested`: kept false; the in-process loop lives in the thread.
  - Icon image loader: use `packaging/videoflow.png` when present; otherwise draw
    a simple generated icon with Pillow.
  - `run_tray(host, port, open_browser)`: builds the supervisor, starts it, then
    runs the `pystray` loop.
  - `tray_available()`: checks the import and, on Linux, whether
    `DISPLAY`/`WAYLAND_DISPLAY` exists.
- `src/videoflow/cli.py`
  - New `tray` subcommand with `--host`, `--port`, and `--no-open`.
  - Defaults match `serve` (settings host/port).
  - If `tray_available()` is false, print a short explanation and fall back to
    the existing `_serve` path with `open=not args.no_open`.

### Menu

- `Open VideoFlow`: opens the browser; starts the service first if stopped.
- `Start service`: enabled when stopped.
- `Stop service`: enabled when running.
- `Restart service`: enabled when running.
- `Status: running|stopped`: disabled text item, refreshed with
  `icon.update_menu()` after lifecycle changes.
- `Quit`: stops the server, then stops the tray.

Starting the tray starts the server and opens the UI by default, matching the
current AppImage behavior. `--no-open` suppresses the initial browser launch.

### Lifecycle details

- PID file is written while the owned server runs and removed on stop. So
  `videoflow status` reports the tray-hosted service.
- `videoflow stop` sends `SIGTERM` to the tray process; that stops the server and
  the tray. This is the accepted trade-off of the one-process design.
- `SIGINT`/`SIGTERM` handlers stop the server and tray cleanly when launched from
  a terminal.
- A healthy VideoFlow service on the same port is replaced through the existing
  `stop_services_on_port` path, never left racing the new one.

### Testing

- Unit tests for `ServerSupervisor` with an injected fake server class: start
  writes the PID, stop joins and removes it, restart calls stop then start, and a
  failed start removes the PID.
- Unit tests for the tray actions with a fake icon: start/stop/restart/open/quit
  call the right supervisor methods and refresh the menu.
- CLI contract test: `tray` parses host/port/`--no-open`; a missing backend falls
  back to `_serve` and prints the guidance.
- No Playwright or UI change.

## Calls made by the builder

- Auto-open on tray start unless `--no-open`; matches the AppImage.
- `Stop` keeps the tray alive; `Quit` exits the process.
- `videoflow stop` terminating the tray process is acceptable for one process.
- No autostart at login in this pass.
- Menu labels and fallback text in English, consistent with the CLI.
