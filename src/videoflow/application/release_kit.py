"""Publish-ready title, description, chapter, hashtag, and thumbnail pack."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.captions import CaptionLine, build_ass_lines
from videoflow.application.fonts import fonts_dir
from videoflow.application.metadata import generate_metadata
from videoflow.application.projects import get_project, load_project_state
from videoflow.application.timeline_meta import load_meta


def build_release_kit(project_id: str) -> dict[str, Any]:
    record = get_project(project_id)
    state = load_project_state(record)
    kept = [
        sentence
        for sentence in state.transcript
        if sentence.id not in set(state.pipeline.discard_sentence_ids)
    ]
    text = " ".join(sentence.text for sentence in kept).strip()
    platform = "youtube"
    metadata = generate_metadata(
        text,
        title=record.name,
        platform=platform,
    )
    meta = load_meta(Path(record.output))
    chapters = [
        {
            "start_sec": round(marker.time_sec, 3),
            "end_sec": round(getattr(marker, "end_sec", 0.0) or 0.0, 3),
            "title": marker.label or marker.id,
        }
        for marker in meta.markers
    ]
    titles = [
        metadata.title,
        f"{metadata.title} | passo a passo",
        f"Como {metadata.title.lower()}",
    ][:3]
    directory = Path(record.output) / "delivery" / "release_kit"
    directory.mkdir(parents=True, exist_ok=True)
    thumbnails = _thumbnails(record.output, state, titles[0], directory)
    payload = {
        "ok": True,
        "project_id": project_id,
        "titles": titles,
        "description": metadata.description,
        "hashtags": list(metadata.hashtags),
        "chapters": chapters,
        "thumbnails": thumbnails,
        "platform": platform,
    }
    target = directory / "release_kit.json"
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    payload["path"] = str(target)
    return payload


def _thumbnails(
    output: Path,
    state: Any,
    title: str,
    directory: Path,
) -> list[dict[str, Any]]:
    media = state.media_info
    if media is None:
        return []
    source = Path(media.source_path).expanduser()
    if not source.is_file():
        return []
    duration = media.duration_frames / max(0.001, media.fps_num / media.fps_den)
    base_style = state.modules_config.shorts.caption_style
    style = base_style.model_copy(
        update={"effect": "static", "font_size": max(56, base_style.font_size)}
    )
    results: list[dict[str, Any]] = []
    for index, ratio in enumerate((0.15, 0.35), start=1):
        time_sec = max(0.2, min(duration - 0.2, duration * ratio))
        ass_path = directory / f"thumb_{index}.ass"
        ass_path.write_text(
            build_ass_lines(
                [CaptionLine(start=0.0, end=1.0, text=title)],
                style=style,
                width=media.width,
                height=media.height,
            ),
            encoding="utf-8",
        )
        target = directory / f"thumbnail_{index}.jpg"
        try:
            FFmpegAdapter().render_thumbnail(
                source,
                target,
                time_sec=time_sec,
                ass_path=ass_path,
                fontsdir=str(fonts_dir()),
            )
        except Exception:  # noqa: BLE001 - thumbnails are advisory
            continue
        results.append(
            {
                "path": str(target),
                "time_sec": round(time_sec, 3),
                "label": f"variant-{index}",
            }
        )
    return results


__all__ = ["build_release_kit"]
