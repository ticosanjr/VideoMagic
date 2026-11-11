"""Research step parameter models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ResearchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(default="", max_length=4000)
    scopes: list[str] = Field(default_factory=list, max_length=20)
    provider_id: str = ""
    search_providers: list[str] = Field(default_factory=list)
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)
    max_results: int = Field(default=6, ge=1, le=30)
    fetch_pages: int = Field(default=3, ge=0, le=20)
    max_cases: int = Field(default=30, ge=1, le=200)
    language: str = Field(default="pt", max_length=20)


class ConsolidateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = ""
    max_cases: int = Field(default=200, ge=1, le=1000)
    require_sources: bool = True
    language: str = Field(default="pt", max_length=20)


class PresenterParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: list[str] = Field(default_factory=list, max_length=50)
    provider_id: str = ""
    max_chars: int = Field(default=200_000, ge=1000, le=2_000_000)


class ScriptParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = ""
    target_words: int = Field(default=1800, ge=100, le=40_000)
    max_sections: int = Field(default=60, ge=1, le=600)
    language: str = Field(default="pt", max_length=20)
    presenter_profile: str = Field(default="", max_length=2000)
    max_cases_per_call: int = Field(default=8, ge=1, le=40)

