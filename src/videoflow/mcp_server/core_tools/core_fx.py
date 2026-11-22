"""VideoFlow core MCP tools: fx."""

from __future__ import annotations

from typing import Any

from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.context import error


def register(register: Any, ctx: Any, legacy: dict[str, Any]) -> None:
    @register
    def vf_depth_composite(
        project_id: str,
        text_or_asset: str,
        start_sec: float,
        end_sec: float,
        style_props: dict[str, Any] | None = None,
        anchor: str = "center",
        width_ratio: float = 0.82,
    ) -> dict[str, Any]:
        """Place text/graphics behind a matted presenter in one time range."""

        from videoflow.application.compositor import depth_composite

        try:
            return depth_composite(
                project_id,
                text_or_asset,
                start_sec,
                end_sec,
                style_props=style_props,
                anchor=anchor,
                width_ratio=width_ratio,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except (OSError, ValueError) as exc:
            return error("depth_composite_failed", str(exc))

    @register
    def vf_pip(
        project_id: str,
        overlay_asset: str,
        start_sec: float,
        end_sec: float,
        anchor: str = "bottom_right",
        corner_radius: int = 24,
        width_ratio: float = 0.28,
        margin_x: int = 32,
        margin_y: int = 32,
        z: int = 25,
    ) -> dict[str, Any]:
        """Add a rounded-window picture-in-picture overlay."""

        from videoflow.application.compositor import picture_in_picture

        try:
            return picture_in_picture(
                project_id,
                overlay_asset,
                start_sec,
                end_sec,
                anchor=anchor,
                corner_radius=corner_radius,
                width_ratio=width_ratio,
                margin_x=margin_x,
                margin_y=margin_y,
                z=z,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except (OSError, ValueError) as exc:
            return error("pip_failed", str(exc))

    @register
    def vf_parallax(
        project_id: str,
        image_path: str,
        start_sec: float,
        end_sec: float,
        bg_scale: float = 1.04,
        fg_scale: float = 1.12,
        rotate_y_deg: float = 3.0,
        width_ratio: float = 0.72,
        z: int = 10,
    ) -> dict[str, Any]:
        """Animate a still as background plus subject 2.5D parallax."""

        from videoflow.application.compositor import parallax

        try:
            return parallax(
                project_id,
                image_path,
                start_sec,
                end_sec,
                bg_scale=bg_scale,
                fg_scale=fg_scale,
                rotate_y_deg=rotate_y_deg,
                width_ratio=width_ratio,
                z=z,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except (OSError, ValueError) as exc:
            return error("parallax_failed", str(exc))

    @register
    def vf_style_preview(
        project_id: str,
        style_id: str,
        duration_sec: float = 5.0,
    ) -> dict[str, Any]:
        """Render a short style card with palette, font, layout, and caption."""

        from videoflow.application.compositor import style_preview

        try:
            return style_preview(project_id, style_id, duration_sec=duration_sec)
        except VideoFlowError as exc:
            return exc.to_dict()
        except (OSError, ValueError) as exc:
            return error("style_preview_failed", str(exc))

    @register
    def vf_fx_depth(
        project_id: str,
        text_or_asset: str,
        start_sec: float,
        end_sec: float,
        style_props: dict[str, Any] | None = None,
        anchor: str = "center",
        width_ratio: float = 0.82,
    ) -> dict[str, Any]:
        """Place a graphic behind the matted presenter with real alpha."""

        from videoflow.application.compositor import depth_composite

        try:
            return depth_composite(
                project_id,
                text_or_asset,
                start_sec,
                end_sec,
                style_props=style_props,
                anchor=anchor,
                width_ratio=width_ratio,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except (OSError, ValueError) as exc:
            return error("fx_depth_failed", str(exc))

    @register
    def vf_fx_parallax(
        project_id: str,
        image_path: str,
        start_sec: float,
        end_sec: float,
        bg_scale: float = 1.04,
        fg_scale: float = 1.12,
        rotate_y_deg: float = 3.0,
        width_ratio: float = 0.72,
        z: int = 10,
    ) -> dict[str, Any]:
        """Animate a still as a 2.5D background plus alpha subject."""

        from videoflow.application.compositor import parallax

        try:
            return parallax(
                project_id,
                image_path,
                start_sec,
                end_sec,
                bg_scale=bg_scale,
                fg_scale=fg_scale,
                rotate_y_deg=rotate_y_deg,
                width_ratio=width_ratio,
                z=z,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except (OSError, ValueError) as exc:
            return error("fx_parallax_failed", str(exc))

    @register
    def vf_fx_motion(
        project_id: str,
        engine: str = "hyperframes",
        template_or_code: str = "",
        props_json: str = "{}",
        duration_sec: float = 5.0,
        alpha: bool = False,
        draft_scale: float = 1.0,
        draft: bool = False,
        width: int = 0,
        height: int = 0,
    ) -> dict[str, Any]:
        """Render an HTML, HyperFrames, Remotion, Manim, or FFmpeg graphic."""

        from videoflow.domains.vision.tools import render_motion_graphic

        try:
            return render_motion_graphic(
                project_id,
                engine=engine,
                template_or_code=template_or_code,
                props_json=props_json,
                duration_sec=duration_sec,
                alpha=alpha,
                draft_scale=draft_scale,
                draft=draft,
                width=width,
                height=height,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except Exception as exc:  # noqa: BLE001 - domain MCP boundary
            return error("fx_motion_failed", str(exc))

    @register
    def vf_fx_capture(
        project_id: str,
        url_or_target: str,
        mode: str = "screenshot",
        duration_sec: float = 3.0,
        crop_selector: str = "",
        css_selector: str = "",
        scroll_animation: str = "",
        output_name: str = "",
        fps: int = 5,
        viewport_width: int = 1440,
        viewport_height: int = 900,
    ) -> dict[str, Any]:
        """Capture a URL or screen as a still or scrollable clip."""

        from videoflow.domains.vision.tools import capture_web_or_screen

        try:
            return capture_web_or_screen(
                project_id,
                url_or_target=url_or_target,
                mode=mode,
                duration_sec=duration_sec,
                crop_selector=crop_selector,
                css_selector=css_selector,
                scroll_animation=scroll_animation,
                output_name=output_name,
                fps=fps,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        except Exception as exc:  # noqa: BLE001 - domain MCP boundary
            return error("fx_capture_failed", str(exc))
