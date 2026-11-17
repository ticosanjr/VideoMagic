"""MCP server exposing the VideoFlow 2.90 audio tools."""

from __future__ import annotations

from mcp.server import MCPServer

from . import tools

TOOL_NAMES = (
    "tts_generate",
    "voice_clean_and_enhance",
    "separate_audio_stems",
    "generate_music_or_sfx",
    "mix_and_master_track",
)


def build_server() -> MCPServer:
    """Build the audio MCP server with the five 2.90 tools."""

    server = MCPServer("VideoFlow Audio", version="2.91.5")
    server.tool(
        name="tts_generate",
        description="Generate a voice-over from text with local TTS or a remote tts capability.",
    )(tools.tts_generate)
    server.tool(
        name="voice_clean_and_enhance",
        description="Remove reverb and noise, then normalize and master a voice recording.",
    )(tools.voice_clean_and_enhance)
    server.tool(
        name="separate_audio_stems",
        description="Separate a mix into vocals and instrumental stems.",
    )(tools.separate_audio_stems)
    server.tool(
        name="generate_music_or_sfx",
        description="Generate a music bed or sound effect locally or through remote compute.",
    )(tools.generate_music_or_sfx)
    server.tool(
        name="mix_and_master_track",
        description="Sidechain-duck music under voice, place SFX, and master to a target LUFS.",
    )(tools.mix_and_master_track)
    return server
