"""Handler registry and optional built-in GPU command integrations."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from gpu_worker.security import is_capability, safe_filename, unique_path

if TYPE_CHECKING:
    from gpu_worker.settings import Settings

Handler = Callable[[dict[str, Any], list[Path], Path], Sequence[str | Path]]

BUILTIN_CAPABILITIES = ("tts", "music", "sfx", "stems", "upscale", "comfyui")
_COMMAND_TIMEOUT_SEC = 3600.0
_COMFYUI_POLL_SEC = 0.5
_COMFYUI_MAX_WAIT_SEC = 3600.0


class HandlerError(RuntimeError):
    """Raised by a handler when a job cannot produce its outputs."""


class HandlerRegistry:
    """Allowlisted capabilities plus their runnable implementations."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}
        self._reasons: dict[str, str] = {
            capability: "handler is not registered" for capability in BUILTIN_CAPABILITIES
        }
        self._lock = threading.RLock()

    def register_handler(self, capability: str, handler: Handler) -> None:
        if not is_capability(capability):
            raise ValueError(f"invalid capability name: {capability!r}")
        if not callable(handler):
            raise TypeError("handler must be callable")
        with self._lock:
            self._handlers[capability] = handler
            self._reasons.pop(capability, None)

    register = register_handler

    def mark_unavailable(self, capability: str, reason: str) -> None:
        if not is_capability(capability):
            raise ValueError(f"invalid capability name: {capability!r}")
        with self._lock:
            if capability not in self._handlers:
                self._reasons[capability] = reason

    def unregister(self, capability: str) -> bool:
        with self._lock:
            removed = self._handlers.pop(capability, None) is not None
            if capability in BUILTIN_CAPABILITIES:
                self._reasons[capability] = "handler is not registered"
            return removed

    def has_capability(self, capability: str) -> bool:
        with self._lock:
            return capability in self._handlers or capability in self._reasons

    def is_available(self, capability: str) -> bool:
        with self._lock:
            return capability in self._handlers

    def get(self, capability: str) -> Handler | None:
        with self._lock:
            return self._handlers.get(capability)

    def reason(self, capability: str) -> str:
        with self._lock:
            return self._reasons.get(capability, "handler is not registered")

    def available(self) -> list[str]:
        with self._lock:
            return sorted(self._handlers)

    def unavailable(self) -> dict[str, str]:
        with self._lock:
            return {
                capability: reason
                for capability, reason in sorted(self._reasons.items())
                if capability not in self._handlers
            }


def command_available(spec: str | None) -> bool:
    """Return whether the first token of a command can be executed."""

    if not spec or not spec.strip():
        return False
    try:
        tokens = shlex.split(spec)
    except ValueError:
        return False
    if not tokens:
        return False
    executable = tokens[0]
    if "{" in executable:
        return True
    if "/" in executable or "\\" in executable:
        path = Path(executable).expanduser()
        return path.is_file() and os.access(path, os.X_OK)
    return shutil.which(executable) is not None


def _expand_command(spec: str, values: Mapping[str, str]) -> list[str]:
    try:
        tokens = shlex.split(spec)
    except ValueError as exc:
        raise HandlerError(f"invalid command template: {exc}") from exc
    if not tokens:
        raise HandlerError("command template is empty")
    expanded: list[str] = []
    for token in tokens:
        if "{" not in token:
            expanded.append(token)
            continue
        try:
            expanded.append(token.format_map(values))
        except KeyError as exc:
            raise HandlerError(f"command template references unknown {exc}") from exc
        except (IndexError, ValueError) as exc:
            raise HandlerError(f"invalid command template token {token!r}: {exc}") from exc
    return expanded


def _run_command(tokens: list[str], work_dir: Path) -> None:
    try:
        completed = subprocess.run(
            tokens,
            cwd=work_dir,
            capture_output=True,
            check=False,
            errors="replace",
            text=True,
            timeout=_COMMAND_TIMEOUT_SEC,
        )
    except FileNotFoundError as exc:
        raise HandlerError(f"command not found: {tokens[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise HandlerError(f"command timed out after {_COMMAND_TIMEOUT_SEC:.0f}s") from exc
    except OSError as exc:
        raise HandlerError(f"command could not start: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        tail = detail[-1][:300] if detail else "no stderr"
        raise HandlerError(f"command exited with status {completed.returncode}: {tail}")


def _make_command_handler(
    spec: str,
    *,
    output_name: str,
    output_dir_name: str = "output",
    require_input: bool = False,
    required_params: tuple[str, ...] = (),
    collect_dir: bool = False,
) -> Handler:
    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> Sequence[str | Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        if require_input and not input_paths:
            raise HandlerError("this capability requires an input artifact")
        for name in required_params:
            value = params.get(name)
            if value is None or (isinstance(value, str) and not value.strip()):
                raise HandlerError(f"params.{name} is required")

        requested_name = params.get("output_name")
        name = (
            safe_filename(str(requested_name), default=output_name)
            if requested_name
            else output_name
        )
        output_path = work_dir / name
        output_dir = work_dir / output_dir_name
        output_dir.mkdir(parents=True, exist_ok=True)

        values: dict[str, str] = {
            "work_dir": str(work_dir),
            "input": str(input_paths[0]) if input_paths else "",
            "output": str(output_path),
            "output_dir": str(output_dir),
        }
        for key, value in params.items():
            if isinstance(value, str | int | float | bool):
                values.setdefault(key, str(value))

        tokens = _expand_command(spec, values)
        if collect_dir:
            if "{output_dir}" not in spec:
                tokens.append(str(output_dir))
        elif "{output}" not in spec:
            tokens.append(str(output_path))

        _run_command(tokens, work_dir)
        if collect_dir:
            results = sorted(path for path in output_dir.rglob("*") if path.is_file())
            if not results:
                raise HandlerError("command produced no output files")
            return results
        if not output_path.is_file():
            raise HandlerError(f"command did not create {output_path.name}")
        return [output_path]

    return handler


def _make_comfyui_handler(base_url: str) -> Handler:
    endpoint = base_url.rstrip("/")

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> Sequence[str | Path]:
        workflow = params.get("workflow")
        if not isinstance(workflow, dict) or not workflow:
            raise HandlerError("params.workflow must be a ComfyUI prompt object")
        timeout_sec = min(
            max(float(params.get("timeout_sec", _COMFYUI_MAX_WAIT_SEC)), 1.0),
            _COMFYUI_MAX_WAIT_SEC,
        )
        work_dir.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout_sec

        with httpx.Client(base_url=endpoint, timeout=30.0) as client:
            response = client.post(
                "/prompt", json={"prompt": workflow, "client_id": uuid.uuid4().hex}
            )
            if response.status_code >= 400:
                raise HandlerError(
                    f"ComfyUI rejected the prompt with status {response.status_code}"
                )
            payload = _json_dict(response)
            prompt_id = str(payload.get("prompt_id") or "")
            if not prompt_id:
                raise HandlerError("ComfyUI did not return a prompt_id")

            outputs: dict[str, Any] = {}
            while time.monotonic() < deadline:
                history = client.get(f"/history/{prompt_id}")
                if history.status_code >= 400:
                    raise HandlerError(f"ComfyUI history failed with status {history.status_code}")
                entry = _json_dict(history).get(prompt_id)
                if isinstance(entry, dict):
                    candidate = entry.get("outputs")
                    if isinstance(candidate, dict) and candidate:
                        outputs = candidate
                        break
                time.sleep(_COMFYUI_POLL_SEC)
            if not outputs:
                raise HandlerError("ComfyUI did not finish before the timeout")

            results: list[Path] = []
            for node_output in outputs.values():
                if not isinstance(node_output, dict):
                    continue
                for values in node_output.values():
                    if not isinstance(values, list):
                        continue
                    for item in values:
                        if not isinstance(item, dict) or not item.get("filename"):
                            continue
                        filename = safe_filename(str(item["filename"]), default="output")
                        download = client.get(
                            "/view",
                            params={
                                "filename": str(item["filename"]),
                                "subfolder": str(item.get("subfolder") or ""),
                                "type": str(item.get("type") or "output"),
                            },
                        )
                        if download.status_code >= 400:
                            raise HandlerError(
                                f"ComfyUI download failed with status {download.status_code}"
                            )
                        destination = unique_path(work_dir, filename)
                        destination.write_bytes(download.content)
                        results.append(destination)
            if not results:
                raise HandlerError("ComfyUI completed without downloadable artifacts")
            return results

    return handler


def _json_dict(response: httpx.Response) -> dict[str, Any]:
    try:
        value = response.json()
    except ValueError as exc:
        raise HandlerError("ComfyUI returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise HandlerError("ComfyUI returned an unexpected JSON payload")
    return value


def _register_command(
    registry: HandlerRegistry,
    *,
    capability: str,
    spec: str | None,
    env_name: str,
    factory: Callable[[str], Handler],
) -> None:
    if not spec:
        registry.mark_unavailable(capability, f"{env_name} is not configured")
        return
    if not command_available(spec):
        registry.mark_unavailable(
            capability, f"command from {env_name} is not executable: {spec.split()[0]}"
        )
        return
    registry.register_handler(capability, factory(spec))


def build_default_registry(settings: Settings) -> HandlerRegistry:
    """Build the registry, marking env-driven capabilities unavailable when missing."""

    registry = HandlerRegistry()
    _register_command(
        registry,
        capability="tts",
        spec=settings.chatterbox_cmd,
        env_name="VF_CHATTERBOX_CMD",
        factory=lambda spec: _make_command_handler(
            spec, output_name="tts.wav", required_params=("text",)
        ),
    )
    _register_command(
        registry,
        capability="music",
        spec=settings.ace_step_cmd,
        env_name="VF_ACE_STEP_CMD",
        factory=lambda spec: _make_command_handler(
            spec, output_name="music.wav", required_params=("prompt",)
        ),
    )
    _register_command(
        registry,
        capability="sfx",
        spec=settings.stable_audio_cmd,
        env_name="VF_STABLE_AUDIO_CMD",
        factory=lambda spec: _make_command_handler(
            spec, output_name="sfx.wav", required_params=("prompt",)
        ),
    )
    _register_command(
        registry,
        capability="stems",
        spec=settings.audio_separator_cmd,
        env_name="VF_AUDIO_SEPARATOR_CMD",
        factory=lambda spec: _make_command_handler(
            spec,
            output_name="stems",
            output_dir_name="stems",
            require_input=True,
            collect_dir=True,
        ),
    )
    _register_command(
        registry,
        capability="upscale",
        spec=settings.realesrgan_cmd,
        env_name="VF_REALESRGAN_CMD",
        factory=lambda spec: _make_command_handler(
            spec, output_name="upscaled.mp4", require_input=True
        ),
    )
    if settings.comfyui_url:
        registry.register_handler("comfyui", _make_comfyui_handler(settings.comfyui_url))
    else:
        registry.mark_unavailable("comfyui", "VF_GPU_COMFYUI_URL is not configured")
    return registry
