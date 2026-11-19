from __future__ import annotations

from videoflow.mcp_server.agent_resources import contracts_dir


def test_contract_docs_are_present() -> None:
    root = contracts_dir()
    expected = {
        "media-contract.md",
        "shorts-batch-schema.md",
        "step-dependencies.md",
        "timeline-protection.md",
        "alpha-matrix.md",
        "qa-modes.md",
        "state-schema-v3.5.md",
        "known-limitations.md",
        "scenes-manifest.md",
        "short-composition-plan.md",
        "output-layout.md",
        "network-offload.md",
    }
    assert expected <= {path.name for path in root.glob("*.md")}
    assert "48,000" in (root / "media-contract.md").read_text(encoding="utf-8")
