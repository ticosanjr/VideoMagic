# VideoFlow 0.22.1

Fix release for the local file browser and service lifecycle.

## Fixed

- The file picker no longer fails with `Internal Server Error` when a folder
  contains an entry with a damaged or out-of-range timestamp. Broken entries are
  skipped, and the picker now offers **Open Home folder** after any listing
  failure.
- Starting the portable build from a directory that no longer exists no longer
  breaks the allowed-root resolution.
- The service stays running after the browser opens. The first launch can take a
  few seconds to unpack the one-file build; the browser now waits for `/health`
  instead of opening too early.
- Opening VideoFlow again while it is already running reuses the running service
  and opens the existing UI.

## Service controls

Use the new buttons in the header:

- **Restart service** restarts the local server and reconnects the UI.
- **Stop service** shuts the server down and tells you that the tab can be
  closed.

From a terminal:

```bash
videoflow status
videoflow restart
videoflow stop
```

The AppImage now starts in your home directory and prints these instructions in
the terminal. If you double-click it from a file manager and no terminal
appears, use the stop button in the UI or `videoflow stop`.

## Artifacts

- `videoflow-0.22.1-linux-x86_64` — SHA-256 `1777bebe82c9e76212c53c21ea640ca9d9a32c0c361595da7f69dd1bcbcf9ddc`
- `VideoFlow-0.22.1-x86_64.AppImage` — SHA-256 `1f869f445de34d949d4b0e4e36312f6a4ae2e8221b241e02e076ba33ba5181e5`

## Run

```bash
chmod +x videoflow-0.22.1-linux-x86_64
./videoflow-0.22.1-linux-x86_64 serve --open
./videoflow-0.22.1-linux-x86_64 status
./videoflow-0.22.1-linux-x86_64 stop
```

The build is lean: speech models are downloaded from the Models tab on first
use. Windows PE is not included because the Windows/Wine build host was
unavailable.
