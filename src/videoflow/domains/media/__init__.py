"""Licensed media discovery and harvesting.

Providers return a normalized candidate with an explicit license status. The
ledger is the source of truth for export: ``unknown`` and unapproved
``fair_use_review`` assets block the final NLE export.
"""

from videoflow.domains.media.download import (
    _clip_bounds,
    _download_http,
    _download_youtube,
    download_asset,
)
from videoflow.domains.media.ledger import (
    ledger_payload,
    license_blockers,
    mark_approved,
    read_ledger,
    write_ledger,
    write_ledger_from_payload,
)
from videoflow.domains.media.models import (
    AssetCandidate,
    _asset_id,
    _candidate,
    classify_license,
)
from videoflow.domains.media.search import (
    PROVIDERS,
    _internet_archive,
    _openverse,
    _pexels,
    _pixabay,
    _wikimedia,
    _youtube,
    search_assets,
)
from videoflow.domains.media.search_base import _check_provider

__all__ = [
    "PROVIDERS",
    "AssetCandidate",
    "_asset_id",
    "_candidate",
    "_check_provider",
    "_clip_bounds",
    "_download_http",
    "_download_youtube",
    "_internet_archive",
    "_openverse",
    "_pexels",
    "_pixabay",
    "_wikimedia",
    "_youtube",
    "classify_license",
    "download_asset",
    "ledger_payload",
    "license_blockers",
    "mark_approved",
    "read_ledger",
    "search_assets",
    "write_ledger",
    "write_ledger_from_payload",
]
