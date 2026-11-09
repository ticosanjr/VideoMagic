"""Licensed media discovery and harvesting.

Providers return a normalized candidate with an explicit license status. The
ledger is the source of truth for export: ``unknown`` and unapproved
``fair_use_review`` assets block the final NLE export.
"""

from videoflow.application.asset_providers.download import (
    _clip_bounds,
    _download_http,
    _download_youtube,
    download_asset,
)
from videoflow.application.asset_providers.ledger import (
    ledger_payload,
    license_blockers,
    mark_approved,
    read_ledger,
    write_ledger,
    write_ledger_from_payload,
)
from videoflow.application.asset_providers.models import (
    AssetCandidate,
    _asset_id,
    _candidate,
    classify_license,
)
from videoflow.application.asset_providers.search import (
    PROVIDERS,
    _check_provider,
    _internet_archive,
    _openverse,
    _pexels,
    _pixabay,
    _wikimedia,
    _youtube,
    search_assets,
)

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
