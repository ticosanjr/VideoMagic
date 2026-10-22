"""OpenAI-compatible text-to-speech client."""

from __future__ import annotations

import subprocess
from pathlib import Path

import httpx

from videoflow.domain.errors import TtsError


class OpenAITtsAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        model: str = "tts-1",
        voice: str = "alloy",
        api_key: str | None = None,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.voice = voice
        self._api_key = api_key or ""
        self.timeout = timeout
        self._transport = transport

    def synthesize(self, text: str, destination: Path, *, speed: float = 1.0) -> Path:
        if not text.strip():
            raise TtsError("Voice-over text is empty.")
        target = Path(destination).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {
            "model": self.model,
            "input": text,
            "voice": self.voice,
            "response_format": "mp3",
            "speed": max(0.25, min(4.0, speed)),
        }
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.post(
                    f"{self.base_url}/audio/speech",
                    headers=headers,
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise TtsError(
                f"Cannot reach the TTS endpoint: {exc.__class__.__name__}"
            ) from exc
        if response.status_code >= 400:
            raise TtsError(
                f"TTS endpoint returned HTTP {response.status_code}: "
                f"{response.text[:200].strip()}"
            )
        if not response.content:
            raise TtsError("TTS endpoint returned empty audio.")
        target.write_bytes(response.content)
        return target


class PiperTtsAdapter:
    """Local Piper CLI adapter. Requires a Piper binary and voice model."""

    def __init__(
        self,
        *,
        binary: str = "piper",
        model_path: str = "",
        timeout: float = 120.0,
    ) -> None:
        self.binary = binary
        self.model_path = model_path
        self.timeout = timeout

    def synthesize(self, text: str, destination: Path, *, speed: float = 1.0) -> Path:
        if not text.strip():
            raise TtsError("Voice-over text is empty.")
        if not self.model_path:
            raise TtsError("Piper requires a local voice model path.")
        target = Path(destination).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.binary,
            "--model",
            self.model_path,
            "--output_file",
            str(target),
        ]
        if abs(speed - 1.0) > 0.01:
            command.extend(["--length_scale", f"{1.0 / max(0.25, min(4.0, speed)):.4f}"])
        try:
            completed = subprocess.run(
                command,
                input=text,
                text=True,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise TtsError(f"Piper binary not found: {self.binary}") from exc
        except subprocess.TimeoutExpired as exc:
            raise TtsError(f"Piper timed out after {self.timeout:.0f}s") from exc
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout).strip()[:300]
            raise TtsError(f"Piper failed: {message}")
        if not target.is_file() or target.stat().st_size == 0:
            raise TtsError("Piper did not write an audio file.")
        return target
