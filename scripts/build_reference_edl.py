#!/usr/bin/env python
"""Build an audio-aligned reference EDL for one raw/edited video pair.

The preferred mode aligns each sentence of the human edit to the raw audio by
global normalized cross-correlation. This chooses the final take even when it is
far from the word-alignment position. The result is validated by reconstructing
the edited audio from the raw source.

Usage:
    uv run python scripts/build_reference_edl.py \
      --raw /home/rafael/Downloads/reference/Raw/Kimi.mp4 \
      --edited /home/rafael/Downloads/reference/edited/Kimik3.1_without_silence.mp4 \
      --edited-transcript /tmp/opencode/human-edit-transcript.json \
      --out Outputs/calibration/reference-edl-kimi.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from videoflow.application.reference_edl import (
    build_reference_edl_from_paths,
    build_reference_edl_from_sentences,
    save_reference_edl,
)
from videoflow.domain.state import Sentence
from videoflow.domains.audio.compare import load_pcm


def _load_sentences(path: Path) -> list[Sentence]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        if "transcript" in payload:
            payload = payload["transcript"]
        elif "sentences" in payload:
            payload = payload["sentences"]
    if not isinstance(payload, list):
        raise ValueError(f"Unsupported transcript payload: {path}")
    return [Sentence.model_validate(item) for item in payload]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--edited", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--edited-transcript", type=Path)
    parser.add_argument("--tau", type=float, default=0.9)
    parser.add_argument("--cut-threshold", type=float, default=0.25)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    name = args.name or args.raw.stem
    if args.edited_transcript is not None:
        sentences = _load_sentences(args.edited_transcript)
        edl = build_reference_edl_from_sentences(
            load_pcm(args.raw),
            load_pcm(args.edited),
            name=name,
            raw_path=args.raw,
            edited_path=args.edited,
            sentences=sentences,
            tau=args.tau,
        )
    else:
        edl = build_reference_edl_from_paths(
            args.raw,
            args.edited,
            name=name,
            tau=args.tau,
            cut_threshold=args.cut_threshold,
        )
    save_reference_edl(args.out, edl)
    payload = edl.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    validation = edl.validation
    diagnostics = edl.diagnostics
    print(f"reference: {args.raw}")
    print(f"edited:    {args.edited}")
    print(f"mode:      {diagnostics.get('mode', 'audio')}")
    print(f"intervals: {len(edl.kept_intervals)}")
    print(f"covered:   {diagnostics.get('covered_seconds')} s")
    print(f"edited:    {diagnostics.get('edited_seconds')} s")
    print(
        "audio_f1:  "
        f"{validation.get('audio_f1')} speech-only "
        f"(all={validation.get('audio_f1_all')}; "
        f"coverage_ref={validation.get('coverage_reference')}, "
        f"coverage_out={validation.get('coverage_output')})"
    )
    print(f"written:   {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
