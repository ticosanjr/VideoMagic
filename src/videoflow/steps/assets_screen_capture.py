"""Capture screenshots from URLs/dashboards as B-roll."""

from __future__ import annotations

import subprocess
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.headless import CapturedAsset
from videoflow.runtime import find_binary
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class ScreenCaptureParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    urls: list[str] = Field(default_factory=list)
    capture: str = Field(default="screenshot", pattern="^(screenshot|clip)$")
    duration_sec: float = Field(default=3.0, gt=0.0, le=60.0)
    viewport_width: int = Field(default=1440, ge=320, le=3840)
    viewport_height: int = Field(default=900, ge=240, le=2160)
    allowed_hosts: list[str] = Field(default_factory=list)


def _browser() -> str | None:
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        binary = find_binary(name)
        if binary:
            return binary
    return None


@register_step
class ScreenCaptureStep(BaseStep):
    type = "assets.screen_capture"
    status = "partial"
    icon = "⛶"
    color = "#0891b2"
    title = "Screen capture"
    description = "Capture a URL/dashboard screenshot with a headless browser for B-roll."
    requires = ()
    produces = ("captured_assets",)
    params_model = ScreenCaptureParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ScreenCaptureParams.model_validate(params)
        browser = _browser()
        if browser is None:
            from videoflow.domain.errors import RecipeError

            raise RecipeError("No Chrome/Chromium binary found for assets.screen_capture")
        output = context.work / "captures"
        output.mkdir(parents=True, exist_ok=True)
        assets: list[CapturedAsset] = []
        for index, url in enumerate(options.urls):
            host = urlparse(url).hostname or ""
            if options.allowed_hosts and host not in options.allowed_hosts:
                context.warnings.append(f"screen capture host not allowed: {host}")
                continue
            target = output / f"capture-{index:02d}.png"
            completed = subprocess.run(
                [
                    browser,
                    "--headless=new",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    f"--window-size={options.viewport_width},{options.viewport_height}",
                    f"--screenshot={target}",
                    url,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0 or not target.is_file():
                context.warnings.append(
                    f"screen capture failed for {url}: {completed.stderr.strip()[-300:]}"
                )
                continue
            assets.append(
                CapturedAsset(
                    kind="screenshot",
                    url=url,
                    path=str(target),
                    width=options.viewport_width,
                    height=options.viewport_height,
                    license="reference",
                    source=host,
                )
            )
        context.metadata["captured_assets"] = [asset.model_dump(mode="json") for asset in assets]
        path = context.work / "captured_assets.json"
        path.write_text(
            __import__("json").dumps([asset.model_dump(mode="json") for asset in assets], indent=2)
            + "\n",
            encoding="utf-8",
        )
        context.artifacts["captured_assets"] = str(path)
        io.report(100, f"{len(assets)} screen capture(s)")
