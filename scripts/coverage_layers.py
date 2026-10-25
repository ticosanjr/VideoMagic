"""Report coverage per layer from the current .coverage data file."""

from __future__ import annotations

from pathlib import Path

import coverage

ROOT = Path(__file__).resolve().parents[1] / "src" / "videoflow"
LAYERS = {
    "api": ROOT / "api",
    "jobs": ROOT / "application" / "jobs.py",
    "exporters": ROOT / "exporters",
    "mcp": ROOT / "mcp_server",
    "steps": ROOT / "steps",
    "application": ROOT / "application",
    "domain": ROOT / "domain",
}


def main() -> int:
    cov = coverage.Coverage()
    cov.load()
    data = cov.get_data()
    measured = [Path(path) for path in data.measured_files()]
    ok = True
    for name, prefix in LAYERS.items():
        files = [
            path
            for path in measured
            if path == prefix or prefix in path.parents
        ]
        total = hits = 0
        for path in files:
            _name, statements, _excluded, missing, _formatted = cov.analysis2(str(path))
            total += len(statements)
            hits += len(statements) - len(missing)
        percent = (hits / total * 100) if total else 0.0
        print(f"{name:12} {hits:5}/{total:<6} {percent:6.2f}%")
        ok = ok and total > 0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
