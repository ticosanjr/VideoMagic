"""Compatibility shim: vision tools live in ``videoflow.domains.vision``.

The package stays importable until the satellite packages are removed, so
``videoflow-mcp-vision`` keeps working while the core uses the internal domain
directly.
"""

from __future__ import annotations

from videoflow.domains.vision import tools as _domain

for _name, _value in vars(_domain).items():
    if not _name.startswith("__"):
        globals()[_name] = _value

del _name, _value
