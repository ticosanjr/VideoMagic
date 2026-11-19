"""Validate an FCPXML handoff without opening Resolve."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from videoflow.exporters.short_fcpxml import validate_short_fcpxml


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--allow-missing-media", action="store_true")
    args = parser.parse_args(argv)
    report = validate_short_fcpxml(
        args.path,
        check_media=not args.allow_missing_media,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
