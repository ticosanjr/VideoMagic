#!/usr/bin/env python
"""Compare a rendered cut with the human reference edit.

Primary metric is audio similarity on the final rendered audio. The report also
includes cut agreement, word agreement, silence, loudness, spectral balance,
word-tail safety, clicks, and sponsor recall.

Usage:
    uv run python scripts/cut_eval.py \
      --reference Outputs/calibration/reference-edl-kimi.json \
      --output /home/rafael/Desktop/Kimi-videoflow \
      --report Outputs/calibration/kimi-baseline.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import numpy as np

from videoflow.application.reference_edl import ReferenceEdl, load_reference_edl
from videoflow.domain.state import ProjectState, Sentence, WordTiming
from videoflow.domains.audio.compare import (
    compare_audio,
    interval_duration,
    interval_f1,
    interval_overlap,
    load_pcm,
    loudness_stats,
    silence_spans,
    silence_stats,
    spectral_correlation,
)

SAMPLE_RATE = 16_000
PROTECTED_STOPWORDS = {
    "a",
    "o",
    "as",
    "os",
    "e",
    "é",
    "mas",
    "então",
    "entao",
    "aí",
    "ai",
    "aqui",
    "agora",
    "quando",
    "porque",
    "isso",
    "isto",
    "ele",
    "ela",
    "eles",
    "elas",
    "você",
    "voce",
    "eu",
    "nós",
    "nos",
    "tem",
    "foi",
    "vai",
    "já",
    "ja",
    "ainda",
    "também",
    "tambem",
    "depois",
    "antes",
    "primeiro",
    "segundo",
    "terceiro",
    "só",
    "so",
    "não",
    "nao",
    "sim",
    "sim.",
    "certo",
    "ok",
}


def _project_path(output: Path, explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit
    if output.is_dir():
        candidate = output / "project_state.json"
        return candidate if candidate.is_file() else None
    candidate = output.parent / "project_state.json"
    return candidate if candidate.is_file() else None


def _video_path(output: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if output.is_dir():
        candidate = output / "exports" / "video.mp4"
        if candidate.is_file():
            return candidate
        matches = sorted((output / "exports").glob("*.mp4"))
        if matches:
            return matches[0]
        raise FileNotFoundError(f"No exported video under {output / 'exports'}")
    return output


def _load_project(path: Path | None) -> ProjectState | None:
    if path is None or not path.is_file():
        return None
    try:
        return ProjectState.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _recipe_intervals(state: ProjectState | None) -> list[tuple[float, float]]:
    if state is None or state.media_info is None:
        return []
    media = state.media_info
    fps = media.fps_num / media.fps_den
    return [
        (segment.source_in_frame / fps, segment.source_out_frame / fps)
        for segment in state.video_segments
        if segment.source_out_frame > segment.source_in_frame
    ]


def _word_key(sentence_id: int, word: WordTiming) -> tuple[int, int, int]:
    return (sentence_id, word.start_sample, word.end_sample)


def _words_inside(
    transcript: list[Sentence],
    intervals: list[tuple[float, float]],
) -> list[tuple[int, WordTiming]]:
    merged = sorted(intervals)
    selected: list[tuple[int, WordTiming]] = []
    for sentence in transcript:
        for word in sentence.words:
            midpoint = (word.start_sample + word.end_sample) / (2 * 48_000)
            for start, end in merged:
                if start > midpoint:
                    break
                if start <= midpoint < end:
                    selected.append((sentence.id, word))
                    break
    return selected


def _word_cut_stats_from_words(
    output_words: list[tuple[int, WordTiming]],
    output_intervals: list[tuple[float, float]],
    *,
    min_tail_ms: int,
) -> dict[str, Any]:
    margins: list[float] = []
    hard_cuts: list[dict[str, Any]] = []
    excluded_timings = 0
    for start, end in sorted(output_intervals):
        credible: list[tuple[int, WordTiming]] = []
        for sentence_id, word in output_words:
            midpoint = (word.start_sample + word.end_sample) / (2 * 48_000)
            if not (start <= midpoint < end):
                continue
            duration = (word.end_sample - word.start_sample) / 48_000
            if duration > 1.5 or word.end_sample / 48_000 > end + 0.3:
                # A word that ends far beyond its clip is an ASR timing
                # artifact, not evidence of a real tail cut.
                excluded_timings += 1
                continue
            credible.append((sentence_id, word))
        if not credible:
            continue
        sentence_id, last = max(credible, key=lambda item: item[1].end_sample)
        margin = end - last.end_sample / 48_000
        margins.append(margin)
        if margin < min_tail_ms / 1000:
            hard_cuts.append(
                {
                    "sentence_id": sentence_id,
                    "word": last.word,
                    "clip_end": round(end, 3),
                    "word_end": round(last.end_sample / 48_000, 3),
                    "margin_ms": round(margin * 1000, 1),
                }
            )
    values = np.asarray(margins, dtype=np.float64) if margins else np.zeros(0)
    return {
        "word_cut_count": len(hard_cuts),
        "excluded_timings": excluded_timings,
        "min_tail_ms": min_tail_ms,
        "tail_margin_ms": {
            "min": round(float(values.min()) * 1000, 1) if values.size else None,
            "p10": round(float(np.percentile(values, 10)) * 1000, 1)
            if values.size
            else None,
            "median": round(float(np.median(values)) * 1000, 1)
            if values.size
            else None,
        },
        "hard_cuts": hard_cuts[:20],
    }


def _word_cut_stats(
    transcript: list[Sentence],
    output_intervals: list[tuple[float, float]],
    *,
    min_tail_ms: int,
) -> dict[str, Any]:
    output_words = _words_inside(transcript, output_intervals)
    return _word_cut_stats_from_words(
        output_words, output_intervals, min_tail_ms=min_tail_ms
    )


def _word_stats(
    transcript: list[Sentence],
    reference_intervals: list[tuple[float, float]],
    output_intervals: list[tuple[float, float]],
    *,
    min_tail_ms: int,
) -> dict[str, Any]:
    reference_words = _words_inside(transcript, reference_intervals)
    output_words = _words_inside(transcript, output_intervals)
    reference_keys = {_word_key(sentence_id, word) for sentence_id, word in reference_words}
    output_keys = {_word_key(sentence_id, word) for sentence_id, word in output_words}
    if reference_keys or output_keys:
        intersection = len(reference_keys & output_keys)
        precision = intersection / len(output_keys) if output_keys else 0.0
        recall = intersection / len(reference_keys) if reference_keys else 0.0
        denominator = precision + recall
        f1 = 2 * precision * recall / denominator if denominator else 0.0
    else:
        precision = recall = f1 = 0.0
        intersection = 0
    cuts = _word_cut_stats_from_words(
        output_words, output_intervals, min_tail_ms=min_tail_ms
    )
    return {
        "reference_words": len(reference_keys),
        "output_words": len(output_keys),
        "intersection": intersection,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        **cuts,
    }


def _reference_text(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return path.read_text(encoding="utf-8", errors="replace")
    if isinstance(payload, dict):
        payload = payload.get("sentences", payload.get("transcript", []))
    if isinstance(payload, list):
        parts: list[str] = []
        for item in payload:
            if isinstance(item, dict):
                if item.get("text"):
                    parts.append(str(item["text"]))
                elif item.get("words"):
                    parts.append(
                        " ".join(
                            str(word.get("word", ""))
                            for word in item["words"]
                            if isinstance(word, dict)
                        )
                    )
        return " ".join(parts)
    return str(payload)


def _protected_terms(text: str) -> list[str]:
    terms: list[str] = []
    terms.extend(re.findall(r"https?://\S+|www\.\S+", text, flags=re.IGNORECASE))
    terms.extend(
        re.findall(
            r"(?:R\$|\$|€|£)\s?\d[\d.,]*|"
            r"\d+[.,]\d+\s*(?:dólares|dolares|reais|milhões|milhoes|bilhões|bilhoes|trilhões|trilhoes)",
            text,
            flags=re.IGNORECASE,
        )
    )
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        tokens = sentence.split()
        for token in tokens[1:]:
            clean = token.strip(".,!?;:()[]{}\"'“”‘’")
            if (
                re.fullmatch(r"[A-ZÀ-Ý][a-zà-ÿ]{2,}", clean)
                and clean.casefold() not in PROTECTED_STOPWORDS
            ):
                terms.append(clean)
    unique: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.casefold().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(term)
    return unique


def _sponsor_stats(
    transcript: list[Sentence],
    reference_intervals: list[tuple[float, float]],
    output_intervals: list[tuple[float, float]],
    reference_text: str,
) -> dict[str, Any] | None:
    if not reference_text.strip():
        return None
    terms = _protected_terms(reference_text)
    if not terms:
        return None
    output_words = _words_inside(transcript, output_intervals)
    output_text = " ".join(word.word for _sentence_id, word in output_words).casefold()
    matched = [term for term in terms if term.casefold() in output_text]
    misses = [term for term in terms if term.casefold() not in output_text]
    return {
        "terms": len(terms),
        "matched": len(matched),
        "recall": round(len(matched) / len(terms), 6),
        "misses": misses[:30],
    }


def _join_clicks(
    pcm: np.ndarray,
    state: ProjectState | None,
    *,
    threshold: float = 0.25,
) -> dict[str, Any]:
    if state is None or not state.audio_segments:
        segments = len(state.audio_segments) if state else 0
        return {"count": 0, "max_delta": None, "segments": segments}
    joins = [
        segment.timeline_out_sample / 48_000
        for segment in state.audio_segments[:-1]
    ]
    deltas: list[float] = []
    for join in joins:
        index = round(join * SAMPLE_RATE)
        if index <= 2 or index >= pcm.size - 1:
            continue
        local = np.abs(np.diff(pcm[max(0, index - 8) : min(pcm.size, index + 8)]))
        baseline = float(np.median(local)) if local.size else 0.0
        delta = abs(float(pcm[index] - pcm[index - 1]))
        if delta > threshold and delta > baseline * 6:
            deltas.append(delta)
    return {
        "count": len(deltas),
        "max_delta": round(max(deltas), 6) if deltas else 0.0,
        "segments": len(state.audio_segments),
    }


def _gate(
    *,
    audio_f1: float,
    cut_f1: float | None,
    word_f1: float | None,
    word_cut_count: int | None,
    silence_delta_ratio: float | None,
    silence_max: float,
    reference_silence_max: float,
    loudness_delta: float | None,
    spectral: float,
    clicks: int,
    sponsor_recall: float | None,
) -> dict[str, bool]:
    return {
        "audio_f1_ge_0_98": audio_f1 >= 0.98,
        "cut_f1_ge_0_98": cut_f1 is None or cut_f1 >= 0.98,
        "word_f1_ge_0_98": word_f1 is None or word_f1 >= 0.98,
        "word_cut_count_zero": word_cut_count is None or word_cut_count == 0,
        "silence_total_within_2pct": silence_delta_ratio is None or silence_delta_ratio <= 0.02,
        "silence_max_near_reference": silence_max <= reference_silence_max + 0.1,
        "loudness_within_1lu": loudness_delta is None or loudness_delta <= 1.0,
        "spectral_ge_0_98": spectral >= 0.98,
        "clicks_zero": clicks == 0,
        "sponsor_recall_ge_0_99": sponsor_recall is None or sponsor_recall >= 0.99,
    }


def _print_report(report: dict[str, Any]) -> None:
    audio = report["audio"]
    cuts = report.get("cuts") or {}
    words = report.get("words") or {}
    silence = report["silence"]
    loudness = report["loudness"]
    sponsor = report.get("sponsor") or {}
    print(f"reference: {report['reference']['edited']}")
    print(f"output:    {report['output']['video']}")
    print(
        f"audio_f1   {audio['audio_f1']:.4f} speech-only "
        f"(all={audio['audio_f1_all']:.4f}; "
        f"ref={audio['coverage_reference']:.4f} "
        f"out={audio['coverage_output']:.4f} "
        f"mean={audio['mean_similarity']:.4f} "
        f"p10={audio['p10_similarity']:.4f})"
    )
    if cuts:
        print(
            f"cut_f1     {cuts['f1']:.4f} "
            f"(precision={cuts['precision']:.4f} recall={cuts['recall']:.4f} "
            f"ref={cuts['reference_seconds']:.1f}s out={cuts['output_seconds']:.1f}s)"
        )
    if words:
        print(
            f"word_f1    {words['f1']:.4f} "
            f"(precision={words['precision']:.4f} recall={words['recall']:.4f})"
        )
    cuts_report = words or report.get("word_cuts")
    if cuts_report:
        print(
            f"word cuts  {cuts_report['word_cut_count']} "
            f"(min tail={cuts_report['tail_margin_ms']['min']} ms, "
            f"median={cuts_report['tail_margin_ms']['median']} ms, "
            f"excluded timings={cuts_report['excluded_timings']})"
        )
    print(
        "silence    "
        f"ref={silence['reference']['total_seconds']:.1f}s "
        f"(max {silence['reference']['max_seconds']:.2f}) "
        f"out={silence['output']['total_seconds']:.1f}s "
        f"(max {silence['output']['max_seconds']:.2f})"
    )
    print(
        "loudness   "
        f"ref={loudness['reference']['lufs']} LUFS / "
        f"{loudness['reference']['true_peak']} dBTP | "
        f"out={loudness['output']['lufs']} LUFS / "
        f"{loudness['output']['true_peak']} dBTP"
    )
    print(f"spectral   {report['spectral_correlation']:.4f}")
    print(f"clicks     {report['clicks']['count']}")
    if sponsor:
        print(
            f"sponsor    {sponsor['matched']}/{sponsor['terms']} "
            f"({sponsor['recall']:.2%})"
        )
    failed = [name for name, ok in report["gates"].items() if not ok]
    print(f"gate       {'PASS' if not failed else 'FAIL: ' + ', '.join(failed)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--reference-video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--reference-transcript", type=Path)
    parser.add_argument("--tau", type=float, default=0.9)
    parser.add_argument("--tolerance", type=float, default=0.15)
    parser.add_argument("--min-tail-ms", type=int, default=60)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.reference_video is None and args.reference is None:
        parser.error("provide --reference (EDL) or --reference-video")
    edl: ReferenceEdl | None = None
    reference_video: Path
    if args.reference_video is not None:
        reference_video = args.reference_video
    else:
        edl = load_reference_edl(args.reference)
        reference_video = Path(edl.edited)
    project_path = _project_path(args.output, args.project)
    video_path = _video_path(args.output, args.video)
    state = _load_project(project_path)
    reference_pcm = load_pcm(reference_video)
    output_pcm = load_pcm(video_path)

    comparison = compare_audio(reference_pcm, output_pcm, tau=args.tau)
    recipe_intervals = _recipe_intervals(state)
    cuts: dict[str, Any] = {}
    if edl is not None:
        cuts = interval_f1(
            edl.kept_intervals,
            recipe_intervals,
            tolerance=args.tolerance,
        )
        cuts["reference_seconds"] = round(interval_duration(edl.kept_intervals), 3)
        cuts["output_seconds"] = round(interval_duration(recipe_intervals), 3)
        cuts["overlap_seconds"] = round(
            interval_overlap(edl.kept_intervals, recipe_intervals), 3
        )
        cuts["reference_intervals"] = len(edl.kept_intervals)
        cuts["output_intervals"] = len(recipe_intervals)

    words: dict[str, Any] | None = None
    word_cuts: dict[str, Any] | None = None
    if state is not None and state.transcript:
        word_cuts = _word_cut_stats(
            state.transcript,
            recipe_intervals,
            min_tail_ms=args.min_tail_ms,
        )
    if state is not None and state.transcript and edl is not None:
        words = _word_stats(
            state.transcript,
            edl.kept_intervals,
            recipe_intervals,
            min_tail_ms=args.min_tail_ms,
        )

    reference_silence = silence_stats(silence_spans(reference_pcm))
    output_silence = silence_stats(silence_spans(output_pcm))
    silence = {
        "reference": reference_silence,
        "output": output_silence,
        "delta_total_seconds": round(
            output_silence["total_seconds"] - reference_silence["total_seconds"], 3
        ),
        "delta_total_ratio": round(
            abs(output_silence["total_seconds"] - reference_silence["total_seconds"])
            / max(1e-9, reference_silence["total_seconds"]),
            6,
        ),
        "delta_max_seconds": round(
            output_silence["max_seconds"] - reference_silence["max_seconds"], 3
        ),
    }
    reference_loudness = loudness_stats(reference_video)
    output_loudness = loudness_stats(video_path)
    lufs_delta: float | None = None
    if (
        reference_loudness["lufs"] is not None
        and output_loudness["lufs"] is not None
    ):
        lufs_delta = abs(float(reference_loudness["lufs"]) - float(output_loudness["lufs"]))
    loudness = {
        "reference": reference_loudness,
        "output": output_loudness,
        "lufs_delta": round(lufs_delta, 6) if lufs_delta is not None else None,
    }
    spectral = spectral_correlation(reference_pcm, output_pcm)
    clicks = _join_clicks(output_pcm, state)
    reference_text = _reference_text(args.reference_transcript)
    sponsor = (
        _sponsor_stats(
            state.transcript if state is not None else [],
            edl.kept_intervals,
            recipe_intervals,
            reference_text,
        )
        if edl is not None
        else None
    )
    gates = _gate(
        audio_f1=comparison.audio_f1,
        cut_f1=cuts.get("f1") if state is not None and cuts else None,
        word_f1=words["f1"] if words else None,
        word_cut_count=(
            words["word_cut_count"]
            if words
            else (word_cuts["word_cut_count"] if word_cuts else None)
        ),
        silence_delta_ratio=silence["delta_total_ratio"],
        silence_max=output_silence["max_seconds"],
        reference_silence_max=reference_silence["max_seconds"],
        loudness_delta=lufs_delta,
        spectral=spectral,
        clicks=clicks["count"],
        sponsor_recall=sponsor["recall"] if sponsor else None,
    )
    report = {
        "reference": {
            "name": edl.name if edl is not None else reference_video.stem,
            "raw": edl.raw if edl is not None else None,
            "edited": str(reference_video),
            "intervals": len(edl.kept_intervals) if edl is not None else 0,
            "duration": round(reference_pcm.size / SAMPLE_RATE, 3),
            "validation": edl.validation if edl is not None else None,
        },
        "output": {
            "video": str(video_path),
            "project": str(project_path) if project_path else None,
            "duration": round(output_pcm.size / SAMPLE_RATE, 3),
        },
        "audio": comparison.to_dict(),
        "cuts": cuts,
        "words": words,
        "word_cuts": word_cuts,
        "silence": silence,
        "loudness": loudness,
        "spectral_correlation": round(spectral, 6),
        "clicks": clicks,
        "sponsor": sponsor,
        "gates": gates,
        "passed": all(gates.values()),
    }
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
