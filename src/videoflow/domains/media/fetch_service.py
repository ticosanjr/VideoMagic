"""Composed fetch service for stock, excerpts and SFX."""

from __future__ import annotations

from .fetch_rip import RipSfxMixin
from .fetch_service_base import FetchServiceBase
from .fetch_stock import StockMixin


class FetchService(StockMixin, RipSfxMixin, FetchServiceBase):
    """Provider orchestration, workspace materialization, and idempotency."""


__all__ = ["FetchService"]
