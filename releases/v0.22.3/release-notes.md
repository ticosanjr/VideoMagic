# VideoFlow 0.22.3

This release makes the workspace tabs visible immediately and ensures a
double-clicked AppImage starts the current UI, not a cached or older page.

## Fixed

- **Visible workspace navigation.** Speech, Edit, Shorts, Studio, Export,
  Models, Services, and Providers now sit in a sticky bar directly under the
  header. They are no longer below the large New project card.
- **Removed a duplicated connection banner** that was accidentally rendered
  inside the header and pushed the page down.
- **Cache-busted UI.** `index.html` and `/` are served with
  `Cache-Control: no-store`; hashed `_app/immutable` assets are immutable.
  The browser is opened with `?v=0.22.3`.
- **Version mismatch warning.** The header shows the server version and the UI
  bundle version. If they differ, a Reload UI banner appears.
- **Repeated double-click protection.** A per-port startup lock means opening
  the AppImage again while it is starting waits for health and opens the
  existing UI instead of starting a competing server.
- **Detached launch tested.** The AppImage was started with no terminal,
  stdin closed, and remained running; `/health`, the static UI, and the
  Services tab all responded.

## Double-click

Make the AppImage executable and double-click it:

```bash
chmod +x VideoFlow-0.22.3-x86_64.AppImage
```

No arguments are required. The AppImage starts the service, waits for
`/health`, and opens `http://127.0.0.1:8765/?v=0.22.3`.

To stop it, use **Stop service** in the header or **Services** tab, or:

```bash
videoflow stop
```

If you prefer a terminal:

```bash
./VideoFlow-0.22.3-x86_64.AppImage serve --open
```

## Tabs

The top bar now always includes:

- Speech
- Edit
- Shorts
- Studio
- Export
- Models
- Services
- Providers

Clicking a tab scrolls directly to its workspace.

## Artifacts

- `videoflow-0.22.3-linux-x86_64` — SHA-256 `707a8698b55d9c7dad60852502a2601af281cbf7136f90f9e63765c058ee063a`
- `VideoFlow-0.22.3-x86_64.AppImage` — SHA-256 `16f6203059a738466fe00d8b73be350e4f4374cbeed342d99cb5604b4589fe20`

The build is lean; speech models are downloaded from the Models tab. Windows PE
is not included because the Windows/Wine build host was unavailable.
