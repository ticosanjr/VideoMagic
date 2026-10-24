# Plugins

A plugin is a folder under `<home>/plugins/<id>` with a `plugin.json` manifest
and an entry module. The core loads it at startup when
`VIDEOWFLOW_PLUGINS` is not `0`.

## Manifest

```json
{
  "id": "acme.otio",
  "name": "ACME OTIO exporter",
  "version": "1.0.0",
  "entry": "plugin.py",
  "enabled": true,
  "permissions": [],
  "provides": ["exporter", "provider"]
}
```

`id` must match `^[a-z0-9][a-z0-9._-]*$`. `permissions` accepts `shell` and
`network`. `provides` is documentation for the UI; the real capability comes
from the registrations the module performs. `api_version` defaults to `1` and a
manifest requiring a newer API is rejected.

## Registration API

```python
from pathlib import Path
from videoflow.plugin_api import register_exporter, register_provider

def write_timeline(state, directory):
    target = Path(directory) / "timeline.acme.json"
    target.write_text("{}", encoding="utf-8")
    return target

register_exporter("acme", write_timeline)
register_provider("llm", {"name": "acme-llm", "model": "local"})
```

Then `export_timeline(state, directory, targets=["acme"])` calls the plugin
writer, and `first_provider("llm")` returns the plugin provider when no
configured provider is available. Panels can be declared with
`register_panel(id, title=..., url=...)`; the Plugins tab lists the panel and
opens it in a new tab. The shell does not embed remote panels.

## Sandbox

`application/plugin_sandbox.py` parses the plugin source **before** importing it
and rejects:

- imports from `subprocess`, `pty`, `multiprocessing`, `socket`, `ssl`,
  `http`, `urllib`, `ftplib`, and `telnetlib` without the matching permission;
- calls such as `eval`, `exec`, `compile`, `__import__`, `os.system`,
  `os.popen`, `os.exec*`, `os.spawn*`, and any `subprocess.*`/`socket.*`.

A blocked plugin is listed with `loaded: false`, a `sandbox` list, and an error.
The check is a static allowlist, not an OS sandbox: a plugin with the `shell`
permission runs with the same user as the service. Install plugins you trust.

## Tests

- `tests/unit/test_plugin_sdk.py` covers exporter and provider registration,
  the shell/network policy, the permission override, and an unknown target.
- `tests/unit/test_advanced_recipe.py` covers step registration.
