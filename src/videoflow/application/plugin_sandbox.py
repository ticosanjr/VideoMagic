"""Static policy check for local plugin entry points.

The check reads the plugin source before it is imported and rejects module
imports and calls that need an explicit manifest permission. It is not a full
Python sandbox; it is an allowlist gate that keeps a plugin from quietly
opening a shell, the network, or arbitrary subprocesses.
"""

from __future__ import annotations

import ast
from pathlib import Path

SHELL_MODULES = {"subprocess", "pty", "multiprocessing"}
NETWORK_MODULES = {"socket", "ssl", "http", "urllib", "ftplib", "telnetlib"}
WRITE_CALLS = {
    "write_text",
    "write_bytes",
    "mkdir",
    "unlink",
    "rename",
    "replace",
    "rmdir",
    "shutil.copy",
    "shutil.copy2",
    "shutil.move",
    "shutil.rmtree",
}
DENIED_CALLS = {
    "os.system",
    "os.popen",
    "os.execv",
    "os.execve",
    "os.spawnl",
    "os.spawnv",
    "eval",
    "exec",
    "__import__",
    "compile",
}


def _imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _calls(tree: ast.AST) -> set[str]:
    calls: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name):
            calls.add(function.id)
        elif isinstance(function, ast.Attribute):
            parts: list[str] = [function.attr]
            value = function.value
            while isinstance(value, ast.Attribute):
                parts.append(value.attr)
                value = value.value
            if isinstance(value, ast.Name):
                parts.append(value.id)
            calls.add(".".join(reversed(parts)))
    return calls


def check_plugin(entry: Path, permissions: list[str]) -> list[str]:
    """Return policy violations for one plugin entry file."""

    source_path = Path(entry)
    try:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        return [f"cannot read plugin source: {exc}"]
    granted = {item.strip().lower() for item in permissions}
    problems: list[str] = []
    for name in _imports(tree):
        root = name.split(".")[0]
        if root in SHELL_MODULES and "shell" not in granted:
            problems.append(f"import {name} needs the 'shell' permission")
        if root in NETWORK_MODULES and "network" not in granted:
            problems.append(f"import {name} needs the 'network' permission")
    for call in _calls(tree):
        if call in DENIED_CALLS and "shell" not in granted:
            problems.append(f"call {call} needs the 'shell' permission")
        if call.split(".")[0] in {"subprocess", "socket"} and "shell" not in granted:
            problems.append(f"call {call} needs the 'shell' permission")
        if call.split(".")[-1] in WRITE_CALLS and "filesystem" not in granted:
            problems.append(f"call {call} needs the 'filesystem' permission")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "open"
            and len(node.args) >= 2
        ):
            mode = node.args[1]
            if (
                isinstance(mode, ast.Constant)
                and isinstance(mode.value, str)
                and any(flag in mode.value for flag in "wax+")
                and "filesystem" not in granted
            ):
                problems.append("call open needs the 'filesystem' permission")
    plugin_dir = Path(source_path).parent.resolve()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for argument in node.args:
            if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
                continue
            candidate = Path(argument.value)
            if not candidate.is_absolute():
                continue
            try:
                candidate.resolve().relative_to(plugin_dir)
            except ValueError:
                problems.append(
                    f"absolute path outside the plugin folder: {argument.value}"
                )
    return sorted(set(problems))
