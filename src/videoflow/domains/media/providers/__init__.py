"""Licensed media providers for the internal media domain."""

# ruff: noqa: F401,F405

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import httpx

from ..errors import InvalidRequestError, ProviderUnavailableError
from .base import (
    AUDIO_SUFFIXES,
    FREESOUND_API,
    IMAGE_SUFFIXES,
    PEXELS_API,
    PIXABAY_API,
    USER_AGENT,
    HttpClient,
    LocalAsset,
    RemoteAsset,
    env_value,
    parse_allowed_hosts,
    safe_filename,
    utc_now,
    validate_external_url,
)
from .freesound import (
    FreesoundClient,
    _pick_freesound_preview,
    freesound_license_filter,
    freesound_license_name,
)
from .local import LocalSfxProvider
from .openverse import OpenverseClient
from .stock import PexelsClient, PixabayClient
from .video import GalleryDLClient, YtDlpClient, find_media_files, format_time
from .wikimedia import WikimediaClient


def resolve_keyed_provider(
    requested: str,
    *,
    env: Mapping[str, str],
    media: str,
    client: httpx.Client | None = None,
) -> tuple[str, PexelsClient | PixabayClient]:
    """Resolve ``auto``/explicit names to an available keyed provider."""

    name = (requested or "auto").strip().lower()
    candidates = ("pexels", "pixabay") if name == "auto" else (name,)
    if name not in {"auto", "pexels", "pixabay"}:
        raise InvalidRequestError(
            f"Unknown provider {requested!r}; use 'auto', 'pexels', or 'pixabay'."
        )
    for candidate in candidates:
        if candidate == "pexels":
            key = env_value(env, "PEXELS_API_KEY")
            if key:
                return candidate, PexelsClient(key, client=client)
        else:
            key = env_value(env, "PIXABAY_API_KEY")
            if key:
                return candidate, PixabayClient(key, client=client)
    needed = "PEXELS_API_KEY or PIXABAY_API_KEY"
    if media == "images":
        needed += " (or enable keyless gallery-dl)"
    raise ProviderUnavailableError(f"No keyed {media} provider is configured; set {needed}.")


def resolve_sfx_provider(
    requested: str,
    *,
    env: Mapping[str, str],
    client: httpx.Client | None = None,
) -> tuple[str, FreesoundClient | LocalSfxProvider]:
    name = (requested or "auto").strip().lower()
    if name not in {"auto", "freesound", "local", "directory"}:
        raise InvalidRequestError(
            f"Unknown SFX provider {requested!r}; use 'auto', 'freesound', or 'local'."
        )
    if name in {"auto", "freesound"}:
        key = env_value(env, "FREESOUND_API_KEY")
        if key:
            return "freesound", FreesoundClient(key, client=client)
        if name == "freesound":
            raise ProviderUnavailableError("FREESOUND_API_KEY is not set.")
    directory = env_value(env, "VF_SFX_DIR")
    if directory and Path(directory).expanduser().is_dir():
        return "local", LocalSfxProvider(directory)
    if name in {"local", "directory"}:
        raise ProviderUnavailableError("VF_SFX_DIR is not set or does not point to a directory.")
    raise ProviderUnavailableError(
        "No SFX provider is configured; set FREESOUND_API_KEY or VF_SFX_DIR."
    )
