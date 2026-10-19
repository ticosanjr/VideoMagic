"""Stable identifiers shared by the domain, the rack, and the docs."""

from typing import Literal

SCHEMA_VERSION: Literal[1] = 1

MODULE_ORDER: tuple[str, ...] = (
    "ingest",
    "vad",
    "transcribe",
    "retakes",
    "jl_cuts",
    "zooms",
    "shorts",
    "export",
)

DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8765
DEFAULT_SECRET_NAME = "VIDEOWFLOW_LLM_API_KEY"
SECRETS_ENV_PATH = "~/.videoflow/secrets.env"
PROMPT_TEMPLATE_VERSION = "retake-v1"
