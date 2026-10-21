"""OpenAI-compatible multimodal chat client."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from videoflow.domain.errors import LlmError


class OpenAIVisionClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key or ""
        self.timeout = timeout
        self._transport = transport

    def analyze(self, frames: list[bytes], prompt: str) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for frame in frames:
            encoded = base64.b64encode(frame).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
                }
            )
        payload = {
            "model": self.model,
            "temperature": 0,
            "stream": False,
            "messages": [{"role": "user", "content": content}],
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise LlmError(
                f"Cannot reach the vision endpoint: {exc.__class__.__name__}"
            ) from exc
        if response.status_code >= 400:
            raise LlmError(
                f"Vision endpoint returned HTTP {response.status_code}: "
                f"{response.text[:200].strip()}"
            )
        try:
            body = response.json()
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LlmError("Vision endpoint returned unusable JSON") from exc
        return _parse_json(text if isinstance(text, str) else json.dumps(text))


def _parse_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LlmError("Vision model did not return JSON") from exc
    if not isinstance(parsed, dict):
        raise LlmError("Vision model did not return an object")
    return parsed
