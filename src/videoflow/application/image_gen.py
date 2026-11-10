"""Optional image generation for synthetic B-roll."""

from __future__ import annotations

import base64
from pathlib import Path

import httpx

from videoflow.application.capabilities import ensure_external_allowed
from videoflow.domain.errors import IngestError


def generate_image(
    prompt: str,
    *,
    base_url: str,
    model: str,
    api_key: str = "",
    seed: int | None = None,
    width: int = 1024,
    height: int = 1024,
    timeout: float = 120.0,
    allow_external_services: bool = False,
    allowed_external_hosts: tuple[str, ...] = (),
) -> bytes:
    """Generate one image through an OpenAI-compatible image endpoint."""

    base = base_url.strip().rstrip("/")
    if not base:
        raise IngestError("Image generation requires a base URL.")
    ensure_external_allowed(
        base,
        capability="image_generation",
        allow_external_services=allow_external_services,
        allowed_hosts=allowed_external_hosts,
    )
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload: dict[str, object] = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": f"{width}x{height}",
        "response_format": "b64_json",
    }
    if seed is not None:
        payload["seed"] = seed
    response = httpx.post(
        f"{base}/images/generations",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise IngestError(
            f"Image generation returned HTTP {response.status_code}: {response.text[:300]}"
        )
    try:
        item = response.json()["data"][0]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise IngestError("Image generation returned an invalid payload.") from exc
    if item.get("b64_json"):
        try:
            return base64.b64decode(str(item["b64_json"]), validate=True)
        except ValueError as exc:
            raise IngestError("Image generation returned invalid base64.") from exc
    url = str(item.get("url") or "")
    if not url:
        raise IngestError("Image generation returned no image data.")
    ensure_external_allowed(
        url,
        capability="image_generation",
        allow_external_services=allow_external_services,
        allowed_hosts=allowed_external_hosts,
    )
    download = httpx.get(url, timeout=timeout)
    if download.status_code >= 400:
        raise IngestError(f"Generated image download returned HTTP {download.status_code}.")
    return download.content


def write_generated(path: Path, data: bytes) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target
