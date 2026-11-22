"""Short download, editing, captions, metadata, thumbnails, voiceover, dubbing and analysis."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405
from .common import _frame_source, _frame_target, _timeline_state_path, fail
from .deps import *
from .models import *


def register_short_routes(app: FastAPI, jobs: JobManager) -> None:
    """Register shorts routes."""

    @app.get("/api/v1/jobs/{job_id}/shorts/{index}")
    def download_short(job_id: str, index: int) -> FileResponse:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        shorts = (job.result or {}).get("shorts") or []
        if not isinstance(shorts, list) or index < 0 or index >= len(shorts):
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "shorts_not_found", "message": str(index)},
            )
        entry = shorts[index]
        raw = entry.get("path") if isinstance(entry, dict) else None
        if not raw:
            raise HTTPException(status_code=404, detail={"ok": False, "code": "shorts_not_found"})
        path = Path(str(raw)).expanduser().resolve()
        output = job.output.expanduser().resolve()
        if not path.is_relative_to(output) or not path.is_file():
            raise HTTPException(
                status_code=403,
                detail={"ok": False, "code": "shorts_not_allowed", "message": "outside output"},
            )
        return FileResponse(path, filename=path.name)

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/edit")
    def edit_short(
        job_id: str, index: int, request: ShortEditRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded" or job.result is None:
            raise StateNotReadyError(
                "The job must succeed before a Short can be edited."
            )
        entry = edit_short_service(
            source=job.source,
            output=job.output,
            index=index,
            result=job.result,
            options=ShortEditOptions(
                title=request.title,
                start_sec=request.start_sec,
                end_sec=request.end_sec,
                aspect_ratio=request.aspect_ratio,
                burn_subtitles=request.burn_subtitles,
                caption_style=request.caption_style,
            ),
        )
        return {
            "ok": True,
            "short": entry,
            "download": f"/api/v1/jobs/{job_id}/shorts/{index}",
        }

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/captions/emoji")
    def short_emoji(
        job_id: str, index: int, request: ShortEmojiRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded" or job.result is None:
            raise StateNotReadyError(
                "The job must succeed before captions can be edited."
            )
        payload = apply_llm_emoji(
            source=job.source,
            output=job.output,
            index=index,
            result=job.result,
            base_url=request.base_url
            or os.environ.get("VIDEOWFLOW_LLM_BASE_URL")
            or "http://localhost:11434/v1",
            model=request.model,
            api_key=os.environ.get("VIDEOWFLOW_LLM_API_KEY"),
            allow_external_services=request.allow_external_services,
            allowed_external_hosts=tuple(request.allowed_external_hosts),
        )
        return {
            "ok": True,
            "emoji_map": payload["emoji_map"],
            "short": payload["short"],
            "download": f"/api/v1/jobs/{job_id}/shorts/{index}",
        }

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/metadata")
    def short_metadata(
        job_id: str, index: int, request: ShortMetadataRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded" or job.result is None:
            raise StateNotReadyError(
                "The job must succeed before metadata can be generated."
            )
        metadata = generate_short_metadata(
            output=job.output,
            index=index,
            result=job.result,
            platform=request.platform,
            tone=request.tone,
            extra_hashtags=tuple(request.extra_hashtags),
            ai=build_intelligence(),
        )
        return {
            "ok": True,
            "metadata": metadata,
            "short": job.result["shorts"][index],
        }

    @app.get("/api/v1/jobs/{job_id}/shorts/{index}/file")
    def download_short_file(job_id: str, index: int) -> FileResponse:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        shorts = (job.result or {}).get("shorts") or []
        if not isinstance(shorts, list) or index < 0 or index >= len(shorts):
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "shorts_not_found", "message": str(index)},
            )
        entry = shorts[index]
        raw = entry.get("path") if isinstance(entry, dict) else None
        if not raw:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "short_file_not_found"},
            )
        path = Path(str(raw)).expanduser().resolve()
        output = job.output.expanduser().resolve()
        if not path.is_relative_to(output) or not path.is_file():
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "short_file_not_found"},
            )
        return FileResponse(path, media_type="video/mp4", filename=path.name)

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/thumbnail")
    def short_thumbnail(
        job_id: str, index: int, request: ShortThumbnailRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded" or job.result is None:
            raise StateNotReadyError(
                "The job must succeed before a thumbnail can be generated."
            )
        thumbnail = generate_short_thumbnail(
            output=job.output,
            index=index,
            result=job.result,
            time_sec=request.time_sec,
            title=request.title,
            caption_style=request.caption_style,
        )
        return {
            "ok": True,
            "thumbnail": thumbnail,
            "short": job.result["shorts"][index],
        }

    @app.get("/api/v1/jobs/{job_id}/shorts/{index}/thumbnail")
    def download_short_thumbnail(job_id: str, index: int) -> FileResponse:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        shorts = (job.result or {}).get("shorts") or []
        if not isinstance(shorts, list) or index < 0 or index >= len(shorts):
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "shorts_not_found", "message": str(index)},
            )
        entry = shorts[index]
        raw = entry.get("thumbnail") if isinstance(entry, dict) else None
        if not raw:
            raise HTTPException(
                status_code=404, detail={"ok": False, "code": "thumbnail_not_found"}
            )
        path = Path(str(raw)).expanduser().resolve()
        output = job.output.expanduser().resolve()
        if not path.is_relative_to(output) or not path.is_file():
            raise HTTPException(
                status_code=403,
                detail={"ok": False, "code": "shorts_not_allowed", "message": "outside output"},
            )
        return FileResponse(
            path,
            filename=path.name,
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/voiceover")
    def short_voiceover(
        job_id: str, index: int, request: ShortVoiceoverRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded" or job.result is None:
            raise StateNotReadyError(
                "The job must succeed before a voice-over can be generated."
            )
        state = ProjectState.model_validate_json(
            (job.output / "project_state.json").read_text(encoding="utf-8")
        )
        stored = state.modules_config.tts
        tts_provider = first_provider("tts") or {}
        tts_defaults = load_settings().tts
        config = TtsConfig(
            provider=request.provider,
            base_url=request.base_url
            or stored.base_url
            or str(tts_provider.get("base_url") or ""),
            model=request.model
            or stored.model
            or str(tts_provider.get("model") or "")
            or tts_defaults.model,
            voice=request.voice or stored.voice or tts_defaults.voice,
            secret_name=stored.secret_name
            or str(tts_provider.get("api_key_env") or "VIDEOWFLOW_TTS_API_KEY"),
            binary=request.binary or stored.binary,
            model_path=request.model_path or stored.model_path,
            speed=request.speed,
            volume=request.volume,
            original_volume=request.original_volume,
        )
        payload = generate_short_voiceover(
            output=job.output,
            index=index,
            result=job.result,
            text=request.text,
            config=config,
            api_key=get_secret(config.secret_name),
            allow_external_services=request.allow_external_services,
            allowed_external_hosts=tuple(request.allowed_external_hosts),
        )
        return {"ok": True, "voiceover": payload, "short": job.result["shorts"][index]}

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/dub")
    def short_dubbing(
        job_id: str, index: int, request: ShortDubbingRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded" or job.result is None:
            raise StateNotReadyError(
                "The job must succeed before dubbing can be generated."
            )
        state = ProjectState.model_validate_json(
            (job.output / "project_state.json").read_text(encoding="utf-8")
        )
        stored_tts = state.modules_config.tts
        tts_provider = first_provider("tts") or {}
        tts_defaults = load_settings().tts
        tts = TtsConfig(
            provider="openai_compatible",
            base_url=request.base_url
            or stored_tts.base_url
            or str(tts_provider.get("base_url") or ""),
            model=request.model
            or stored_tts.model
            or str(tts_provider.get("model") or "")
            or tts_defaults.model,
            voice=request.voice or stored_tts.voice or tts_defaults.voice,
            secret_name=stored_tts.secret_name
            or str(tts_provider.get("api_key_env") or "VIDEOWFLOW_TTS_API_KEY"),
            speed=request.speed,
            volume=request.volume,
            original_volume=request.original_volume,
        )
        dubbing = DubbingConfig(
            target_language=request.target_language,
            original_volume=request.original_volume,
        )
        payload = generate_short_dubbing(
            output=job.output,
            index=index,
            result=job.result,
            source_text=request.text,
            target_language=request.target_language,
            tts=tts,
            dubbing=dubbing,
            llm_base_url=(
                request.llm_base_url
                or state.modules_config.retakes.base_url
                or str((first_provider("llm") or {}).get("base_url") or "")
                or "http://localhost:11434/v1"
            ),
            llm_model=request.llm_model
            or state.modules_config.retakes.model_name
            or str((first_provider("llm") or {}).get("model") or ""),
            llm_api_key=get_secret("VIDEOWFLOW_LLM_API_KEY"),
            tts_api_key=get_secret(tts.secret_name),
            allow_external_services=request.allow_external_services,
            allowed_external_hosts=tuple(request.allowed_external_hosts),
        )
        return {"ok": True, "dubbing": payload, "short": job.result["shorts"][index]}

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/analyze/llm")
    def analyze_short_vision(
        job_id: str, index: int, request: ShortVisionRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded" or job.result is None:
            raise StateNotReadyError("The job must succeed before analysis.")
        vision = first_provider("vision") or {}
        base_url = (
            request.base_url
            or os.environ.get("VIDEOWFLOW_VISION_BASE_URL")
            or str(vision.get("base_url") or "")
        )
        if not base_url:
            raise CapabilityUnavailableError(
                "external_vision",
                "Configure a vision endpoint or VIDEOWFLOW_VISION_BASE_URL.",
            )
        analysis = analyze_short_llm_entry(
            output=job.output,
            index=index,
            result=job.result,
            base_url=base_url,
            model=request.model
            or str(vision.get("model") or "")
            or os.environ.get("VIDEOWFLOW_VISION_MODEL", "gpt-4o-mini"),
            api_key=get_secret(
                str(vision.get("api_key_env") or "VIDEOWFLOW_VISION_API_KEY")
            ),
            allow_external_services=request.allow_external_services,
            allowed_external_hosts=tuple(request.allowed_external_hosts),
            max_frames=request.max_frames,
        )
        return {
            "ok": True,
            "analysis": analysis,
            "short": job.result["shorts"][index],
        }

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/analyze")
    def analyze_short(job_id: str, index: int) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded" or job.result is None:
            raise StateNotReadyError("The job must succeed before analysis.")
        analysis = analyze_short_entry(
            output=job.output,
            index=index,
            result=job.result,
        )
        return {
            "ok": True,
            "analysis": analysis,
            "short": job.result["shorts"][index],
        }
