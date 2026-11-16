"""Subprocess helpers that build argv lists and never use a shell."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Any

from .errors import CommandFailedError, InvalidArgumentError, MissingCommandError


@dataclass(frozen=True)
class CommandResult:
    """Captured result of one external command."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def expand_template(
    template: str,
    values: Mapping[str, Any],
    *,
    name: str = "command",
) -> list[str]:
    """Expand a command template into a safe argv list.

    `shlex.split` runs before placeholder substitution so text containing
    spaces or shell metacharacters stays a single argument. A token that is
    exactly an empty placeholder is dropped, which lets optional flags omit
    themselves; embedded empty placeholders are rejected.
    """

    try:
        tokens = shlex.split(template)
    except ValueError as exc:
        raise InvalidArgumentError(
            f"{name} template is not valid shell syntax: {exc}",
            details={"template": template},
        ) from exc
    if not tokens:
        raise InvalidArgumentError(f"{name} template is empty", details={"template": template})

    argv: list[str] = []
    for token in tokens:
        try:
            fields = [field for _, field, _, _ in Formatter().parse(token) if field]
        except ValueError as exc:
            raise InvalidArgumentError(
                f"{name} template has invalid braces: {exc}",
                details={"template": template},
            ) from exc

        unknown = sorted({field for field in fields if field not in values})
        if unknown:
            raise InvalidArgumentError(
                f"{name} template uses unknown placeholder(s): {', '.join(unknown)}",
                details={"template": template, "placeholders": unknown},
            )

        if len(fields) == 1 and token == "{" + fields[0] + "}":
            value = values[fields[0]]
            if value is None or value == "":
                continue

        try:
            argv.append(token.format(**values))
        except (KeyError, IndexError, ValueError) as exc:
            raise InvalidArgumentError(
                f"{name} template could not be expanded: {exc}",
                details={"template": template},
            ) from exc

    if not argv:
        raise InvalidArgumentError(
            f"{name} template produced no arguments", details={"template": template}
        )
    return argv


def run(
    argv: Sequence[str],
    *,
    timeout: float = 1800.0,
    cwd: str | Path | None = None,
) -> CommandResult:
    """Run an argv list without a shell and raise typed errors on failure."""

    if not argv:
        raise InvalidArgumentError("command argv must not be empty")
    command = [str(part) for part in argv]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            check=False,
        )
    except FileNotFoundError as exc:
        raise MissingCommandError(
            f"executable not found: {command[0]}",
            details={"executable": command[0]},
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise CommandFailedError(
            f"command timed out after {timeout:g}s: {command[0]}",
            argv=command,
            returncode=-1,
        ) from exc

    result = CommandResult(
        argv=tuple(command),
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )
    if completed.returncode != 0:
        raise CommandFailedError(
            f"command failed with exit code {completed.returncode}: {command[0]}",
            argv=command,
            returncode=completed.returncode,
            stderr=result.stderr,
        )
    return result


def resolve_binary(*names: str, env: str | None = None) -> str | None:
    """Return the first available executable from an env override or `PATH`."""

    if env:
        configured = os.environ.get(env)
        if configured:
            return configured
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None
