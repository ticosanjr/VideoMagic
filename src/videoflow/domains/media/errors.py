"""Typed errors for the fetch MCP server."""

from __future__ import annotations

from typing import Any


class McpFetchError(Exception):
    """Base class for actionable fetch failures."""

    code = "MCP_FETCH_ERROR"

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail}


class InvalidRequestError(McpFetchError):
    """The tool arguments are invalid."""

    code = "INVALID_REQUEST"


class ProviderUnavailableError(McpFetchError):
    """The requested provider cannot run in this environment."""

    code = "PROVIDER_UNAVAILABLE"


class ProviderResponseError(McpFetchError):
    """A provider returned an unusable response."""

    code = "PROVIDER_RESPONSE"


class DownloadError(McpFetchError):
    """A remote asset could not be downloaded."""

    code = "DOWNLOAD_FAILED"


class UrlNotAllowedError(McpFetchError):
    """A URL failed the scheme or host allowlist."""

    code = "URL_NOT_ALLOWED"


class WorkspaceError(McpFetchError):
    """The workspace path or asset could not be created."""

    code = "WORKSPACE_ERROR"
