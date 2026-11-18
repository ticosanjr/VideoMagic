"""MCP server exposing the VideoFlow 2.90 vision tools."""

from __future__ import annotations

from mcp.server import MCPServer

from . import tools

TOOL_NAMES = (
    "transcribe_word_aligned",
    "remove_background",
    "upscale_media",
    "render_motion_graphic",
    "image_to_broll_motion",
    "capture_web_or_screen",
)


def build_server() -> MCPServer:
    """Build the vision MCP server with the five 2.90 tools."""

    server = MCPServer("VideoFlow Vision", version="3.0.4")
    server.tool(
        name="transcribe_word_aligned",
        description="Transcribe word-aligned captions to JSON, SRT, and ASS.",
    )(tools.transcribe_word_aligned)
    server.tool(
        name="remove_background",
        description="Remove the background from an image or video with rembg.",
    )(tools.remove_background)
    server.tool(
        name="upscale_media",
        description="Upscale an image or video with remote compute, Real-ESRGAN, or FFmpeg.",
    )(tools.upscale_media)
    server.tool(
        name="render_motion_graphic",
        description=(
            "Render a Remotion, Manim, FFmpeg, HTML, or HyperFrames graphic "
            "with optional alpha and draft scale."
        ),
    )(tools.render_motion_graphic)
    server.tool(
        name="image_to_broll_motion",
        description="Turn a still image into a zoom or pan B-roll clip.",
    )(tools.image_to_broll_motion)
    server.tool(
        name="capture_web_or_screen",
        description="Capture a URL or screen target as a still or a B-roll clip.",
    )(tools.capture_web_or_screen)
    return server
