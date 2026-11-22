"""ComfyUI polling handler for the GPU worker."""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx

from gpu_worker.handler_types import Handler, HandlerError
from gpu_worker.security import safe_filename, unique_path

_COMFYUI_POLL_SEC = 0.5
_COMFYUI_MAX_WAIT_SEC = 3600.0


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
