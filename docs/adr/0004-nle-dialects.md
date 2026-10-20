# ADR-0004 — One timeline, three NLE dialects

Status: accepted. Revised for 0.20.1. Date: 2026-10-19.

## Context

The brief claims FCPXML "is natively compatible with DaVinci Resolve Studio and
Premiere Pro". Current Adobe documentation says Premiere cannot import FCPXML
directly; its interchange is FCP 7 XML. Kdenlive writes its own native MLT XML
(`.kdenlive`) and OTIO import proved unreliable across installed versions.
Resolve imports FCPXML 1.9 reliably and 1.10 in newer releases; FCPXML 1.9
requires the media URL in a `media-rep` child, not the old asset `src`.

Shipping one file and claiming three apps would fail AC-06 on day one.

## Decision

- One immutable timeline model.
- Resolve: FCPXML 1.9 by default, 1.10 optional.
- Premiere: xmeml version 4 (FCP 7 XML) with full file definitions and A/V links.
- Kdenlive: native `.kdenlive` MLT XML.
- `videoflow_export_fcpxml` keeps its name but takes `target_nle`.
- A compatibility spike with three minimal timelines gates the dialect.
- The manual import check is a release artifact.

## Consequences

- Three writers, one source of truth.
- The v1 xmeml writer must carry separate audio and video tracks for J-cuts,
  full `<file>` definitions on every clipitem, and explicit link groups.
- Some attributes are version-sensitive. The spike decides, not guesswork.
- The API response names artifacts by target, not by a single file.
- OTIO remains a library helper, not the Kdenlive deliverable.
- A future native `.drp` or `.prproj` writer does not change this contract.

## Alternatives rejected

- FCPXML only: fails Premiere.
- AAF: heavier and not needed for the v1 feature set.
- Convert through Resolve: requires the app, which defeats headless operation.
