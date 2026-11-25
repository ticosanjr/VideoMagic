"""VideoFlow core MCP tools: preflight and transcript insights."""

from __future__ import annotations

from typing import Any

from videoflow.application.projects import get_project, load_project_state
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.context import error, unknown_action


def register(register: Any, ctx: Any, legacy: dict[str, Any]) -> None:
    @register
    def vf_preflight_plan(
        project_id: str,
        operation: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Validate schema, dependencies, licenses, disk, GPU, and cost."""

        from videoflow.application.preflight_plan import build_preflight_plan

        try:
            return build_preflight_plan(project_id, operation, params)
        except VideoFlowError as exc:
            return exc.to_dict()
        except (OSError, ValueError) as exc:
            return error("preflight_failed", str(exc))

    @register
    def vf_transcript_query(
        project_id: str,
        query: str = "",
        source_id: str = "",
        start_sec: float = 0.0,
        end_sec: float = 0.0,
        sentence_range: str = "",
        include_words: bool = False,
        limit: int = 50,
        cursor: int = 0,
    ) -> dict[str, Any]:
        """Search or page through the cleaned transcript without dumping it."""

        try:
            record = get_project(project_id)
            state = load_project_state(record)
        except VideoFlowError as exc:
            return exc.to_dict()
        rate = (
            state.media_info.audio_sample_rate
            if state.media_info is not None
            else 48000
        )
        start_sample = round(max(0.0, float(start_sec)) * rate) if start_sec else 0
        end_sample = round(max(0.0, float(end_sec)) * rate) if end_sec else 0
        range_start = range_end = None
        if sentence_range:
            try:
                left, right = sentence_range.replace(":", "-").split("-", 1)
                range_start = int(left)
                range_end = int(right)
            except (TypeError, ValueError):
                return error(
                    "invalid_sentence_range",
                    "sentence_range must look like '30-50'",
                )
        text_query = str(query or "").strip().casefold()
        discarded = set(state.pipeline.discard_sentence_ids)
        selected = []
        for sentence in state.transcript:
            if sentence.id in discarded:
                continue
            if range_start is not None and not (range_start <= sentence.id <= range_end):
                continue
            if start_sample and sentence.end_sample <= start_sample:
                continue
            if end_sample and sentence.start_sample >= end_sample:
                continue
            if text_query and text_query not in sentence.text.casefold():
                continue
            selected.append(sentence)
        page_size = max(1, min(int(limit), 500))
        offset = max(0, int(cursor))
        page = selected[offset : offset + page_size]
        items = []
        for sentence in page:
            item: dict[str, Any] = {
                "id": sentence.id,
                "start": round(sentence.start_sample / rate, 3),
                "end": round(sentence.end_sample / rate, 3),
                "text": sentence.text,
                "speaker": sentence.speaker,
            }
            if include_words:
                item["words"] = [
                    {
                        "word": word.word,
                        "start": round(word.start_sample / rate, 3),
                        "end": round(word.end_sample / rate, 3),
                        "probability": round(word.probability, 3),
                    }
                    for word in sentence.words
                ]
            items.append(item)
        next_cursor = offset + len(items) if offset + len(items) < len(selected) else None
        result: dict[str, Any] = {
            "ok": True,
            "project_id": project_id,
            "count": len(selected),
            "returned": len(items),
            "cursor": offset,
            "next_cursor": next_cursor,
            "sentences": items,
        }
        if source_id:
            result["warning"] = "source_id is not attached to transcript sentences yet"
        return result

    @register
    def vf_transcript(
        action: str = "query",
        project_id: str = "",
        query: str = "",
        source_id: str = "",
        start_sec: float = 0.0,
        end_sec: float = 0.0,
        sentence_range: str = "",
        include_words: bool = False,
        limit: int = 500,
        cursor: int = 0,
    ) -> dict[str, Any]:
        """Query all transcript sentences or return the edited editorial map."""

        if action == "query":
            return vf_transcript_query(
                project_id=project_id,
                query=query,
                source_id=source_id,
                start_sec=start_sec,
                end_sec=end_sec,
                sentence_range=sentence_range,
                include_words=include_words,
                limit=limit,
                cursor=cursor,
            )
        if action == "editorial_map":
            from videoflow.application.transcript import build_editorial_map

            try:
                record = get_project(project_id)
                state = load_project_state(record)
                payload = build_editorial_map(state, project_dir=record.output)
                payload["project_id"] = project_id
                return payload
            except VideoFlowError as exc:
                return exc.to_dict()
        return unknown_action("vf_transcript", action, ("query", "editorial_map"))

    @register
    def vf_gpu_preflight(require_gpu: bool = False) -> dict[str, Any]:
        """Validate the Windows GPU worker before a long job."""

        from videoflow.application.compute import router_from_settings
        from videoflow.application.settings import load_settings

        try:
            settings = load_settings()
            router = router_from_settings(settings)
            health = router.health(force=True)
            probe: dict[str, Any] = {}
            if health.available:
                try:
                    probe = router.client.probe()
                except Exception:  # noqa: BLE001 - probe is advisory
                    probe = {}
            if not health.available and require_gpu:
                return error(
                    "gpu_worker_unreachable",
                    "Windows GPU worker is not reachable.",
                    fix_hint="Start the worker on Windows or switch compute mode to local.",
                    worker_url=router.worker_url,
                    health=health.model_dump(mode="json"),
                )
            return {
                "ok": True,
                "remote_available": bool(health.available),
                "degraded": not bool(health.available),
                "degraded_reason": (
                    "" if health.available else "windows_gpu_offline_fallback_cpu"
                ),
                "mode": router.mode,
                "transport": getattr(router, "transport", "auto"),
                "worker_source": getattr(router, "worker_source", "none"),
                "worker_url": router.worker_url,
                "health": health.model_dump(mode="json"),
                "probe": probe,
            }
        except Exception as exc:  # noqa: BLE001 - preflight must return a payload
            if require_gpu:
                return error(
                    "gpu_worker_unreachable",
                    str(exc),
                    fix_hint="Check the GPU settings and worker status.",
                )
            return {
                "ok": True,
                "remote_available": False,
                "degraded": True,
                "degraded_reason": f"gpu_preflight_failed: {exc}",
                "mode": "local",
                "transport": "auto",
                "worker_url": "",
                "health": {},
                "probe": {},
            }
