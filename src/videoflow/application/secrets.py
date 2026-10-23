"""Secret storage: environment, OS keyring, then a 0600 local fallback.

Secret values are never returned by the API. Only presence is reported.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
from pathlib import Path

from videoflow.runtime import portable_home

SERVICE = "videoflow"
SECRETS_FILE = "secrets.json"


def _fallback_path() -> Path:
    return portable_home() / SECRETS_FILE


def _read_fallback() -> dict[str, str]:
    path = _fallback_path()
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


def _write_fallback(values: dict[str, str]) -> None:
    path = _fallback_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    with contextlib.suppress(OSError):
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _keyring():
    try:
        import keyring

        return keyring
    except Exception:
        return None


def get_secret(name: str) -> str:
    if not name:
        return ""
    env = os.environ.get(name)
    if env:
        return env
    keyring = _keyring()
    if keyring is not None:
        try:
            value = keyring.get_password(SERVICE, name)
            if value:
                return str(value)
        except Exception:
            pass
    return _read_fallback().get(name, "")


def set_secret(name: str, value: str) -> None:
    if not name:
        raise ValueError("Secret name is empty.")
    keyring = _keyring()
    if keyring is not None:
        try:
            keyring.set_password(SERVICE, name, value)
            return
        except Exception:
            pass
    values = _read_fallback()
    values[name] = value
    _write_fallback(values)


def delete_secret(name: str) -> None:
    keyring = _keyring()
    if keyring is not None:
        with contextlib.suppress(Exception):
            keyring.delete_password(SERVICE, name)
    values = _read_fallback()
    if values.pop(name, None) is not None:
        _write_fallback(values)


def secret_present(name: str) -> bool:
    return bool(get_secret(name))


def secret_backend() -> str:
    if _keyring() is not None:
        try:
            backend = _keyring().get_keyring()
            if backend is not None:
                return f"keyring:{backend.__class__.__name__}"
        except Exception:
            pass
    return "file:0600"
