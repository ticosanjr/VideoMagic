# ADR 0011: Use an allowlisted local filesystem browser

## Status

Accepted for 0.20.0.

## Context

The rack runs in a browser and the pipeline runs in a local Python server. A
browser `<input type="file">` does not expose the absolute path of a selected
file. Using it would require uploading or copying a multi-gigabyte video into
the server before FFmpeg could read it.

The server already has the correct security boundary for local paths:
`resolve_allowed` and `VIDEOWFLOW_ALLOWED_ROOTS`. A native OS dialog would need
platform-specific helpers (`zenity`, PowerShell, or an Electron/Tauri wrapper),
which adds deployment and test complexity without improving the path jail.

## Decision

Add a server-backed filesystem browser:

- `GET /api/v1/fs/roots` returns the allowlisted roots.
- `GET /api/v1/fs/list` lists one directory with file-extension filters,
  search, hidden-file control, breadcrumbs, and writable state.
- `POST /api/v1/fs/mkdir` creates one validated child directory.
- `GET /api/v1/media/probe` returns FFprobe metadata for a selected media file.
- The UI uses a modal `PathPicker.svelte` for source, output, SRT, and model
  paths. Typed paths remain under an advanced disclosure.

## Security invariants

- Every requested path passes `resolve_allowed` before it is read or written.
- Every listed entry is resolved before being returned. Symlinks that escape a
  root are omitted; direct access to one is rejected.
- Names for new directories are single portable segments. Separators, dot-only
  names, control characters, Windows reserved names, and trailing spaces/dots
  are rejected.
- The browser never uploads media and exposes no arbitrary download endpoint.
- Adding a new location requires an operator change to
  `VIDEOWFLOW_ALLOWED_ROOTS`.

## Consequences

- The UI can select files without copying them.
- The path picker works on Linux and Windows because paths are just strings
  returned by the same API.
- The browser adds a read-only filesystem surface that must keep the same path
  jail tests as job inputs.
- A remote browser would browse the server's filesystem, not the client's. That
  is correct for a local-only product and is another reason not to expose the
  port.
