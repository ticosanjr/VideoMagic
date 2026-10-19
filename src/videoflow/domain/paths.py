"""Local path jail.

VideoFlow is a single-user tool with no login. The boundary is the set of
directories the operator configured. ``Path.resolve()`` follows symlinks, so a
link inside an allowed root that points outside it is rejected.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from videoflow.domain.errors import PathJailError


def resolve_allowed(path: Path, roots: Sequence[Path]) -> Path:
    """Resolve ``path`` and return it only if it stays inside one allowed root."""

    if not roots:
        raise PathJailError(str(path))
    resolved = path.expanduser().resolve(strict=False)
    for root in roots:
        root_resolved = root.expanduser().resolve(strict=False)
        if resolved == root_resolved or resolved.is_relative_to(root_resolved):
            return resolved
    raise PathJailError(str(path))
