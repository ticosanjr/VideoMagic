"""Search configuration resolution."""

from __future__ import annotations

from videoflow.application.settings import AppSettings, SearchSettings, load_settings


def _search_config(settings: AppSettings | SearchSettings | None) -> SearchSettings:
    if isinstance(settings, AppSettings):
        return settings.search
    if isinstance(settings, SearchSettings):
        return settings
    return load_settings().search
