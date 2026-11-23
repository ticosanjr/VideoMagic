# DaVinci Resolve Studio bridge

The Resolve adapter is optional and detected at runtime. VideoFlow never imports
Resolve at module import time; when Resolve or External Scripting is unavailable,
the static FCPXML export remains the supported path.

## Prerequisites

- DaVinci Resolve Studio is running.
- `Preferences → System → General → External scripting using` is set to
  `Local`.
- `RESOLVE_SCRIPT_API` and `RESOLVE_SCRIPT_LIB` point at the Resolve scripting
  installation.
- The configured Python can `import DaVinciResolveScript`.

## Scope

- Push: write FCPXML and import it through the Resolve API.
- Pull: read timeline markers and track items.
- Sync: apply `nle.sync_back` from the external timeline.
- Not supported: arbitrary Fusion/color node roundtrip, effect graph mapping, or
  editing Resolve project settings.

The 2.90 release gate requires a manual evidence JSON from this command on the
machine with Resolve Studio installed.
