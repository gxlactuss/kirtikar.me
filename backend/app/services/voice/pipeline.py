"""Voice Station: Audio pre-processing and Indic speech translation via Sarvam AI."""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("app.services.voice.pipeline")

SARVAM_API_URL = "https://api.sarvam.ai/speech-to-text-translate"


@dataclass(frozen=True)
class VoiceTranscriptionResult:
    transcript: str
    language_code: str
    duration_seconds: float
    # False when the text below is the canned fallback rather than a real
    # transcription, so callers can tell a working demo from a silent failure.
    used_live_api: bool = False


class VoiceStation:
    """Production Voice Station: Ingests artisan speech audio and produces English translation."""

    def __init__(self, api_key: Optional[str] = None, timeout_seconds: float = 30.0):
        self.api_key = api_key or settings.SARVAM_API_KEY
        self.timeout_seconds = timeout_seconds

    def process_audio(
        self,
        audio_path: Path,
        allow_synthetic_fallback: bool = True,
    ) -> VoiceTranscriptionResult:
        """Transcribe and translate an artisan voice note to English."""
        if not audio_path.exists():
            if allow_synthetic_fallback:
                logger.info("Physical audio file not found, returning synthetic voice output: %s", audio_path)
                return self._synthetic_fallback()
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        file_size = audio_path.stat().st_size
        if file_size == 0:
            raise ValueError("Audio file is empty (0 bytes)")

        # If Sarvam API key is configured, call live API
        if self.api_key:
            try:
                return self._call_sarvam_api(audio_path)
            except httpx.HTTPStatusError as e:
                logger.warning("Sarvam AI STT HTTP error %s: %s", e.response.status_code, e.response.text)
                if allow_synthetic_fallback:
                    logger.info("Falling back to synthetic transcription after API failure")
                    return self._synthetic_fallback()
                raise
            except Exception as e:
                logger.warning("Sarvam AI STT API call failed: %s", e)
                if allow_synthetic_fallback:
                    logger.info("Falling back to synthetic transcription after API failure")
                    return self._synthetic_fallback()
                raise

        # No API key provided: use fallback
        if allow_synthetic_fallback:
            return self._synthetic_fallback()

        raise RuntimeError("Sarvam AI API key is missing and synthetic fallback is disabled")

    def _call_sarvam_api(self, audio_path: Path) -> VoiceTranscriptionResult:
        headers = {
            "api-subscription-key": self.api_key,
        }

        ext = audio_path.suffix.lower()
        content_type = "audio/wav"
        if ext == ".mp3":
            content_type = "audio/mpeg"
        elif ext in (".m4a", ".mp4"):
            content_type = "audio/mp4"
        elif ext == ".ogg":
            content_type = "audio/ogg"

        with open(audio_path, "rb") as f:
            files = {
                "file": (audio_path.name, f, content_type),
            }
            data = {
                "model": "saaras:v3",
            }
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(SARVAM_API_URL, headers=headers, files=files, data=data)
                response.raise_for_status()
                payload = response.json()

        transcript = payload.get("transcript", "").strip()
        language_code = payload.get("language_code", "hi")
        duration_val = payload.get("duration")
        duration = float(duration_val) if duration_val is not None else 0.0

        if not transcript:
            raise ValueError("Sarvam AI returned empty transcript")

        return VoiceTranscriptionResult(
            transcript=transcript,
            language_code=language_code,
            duration_seconds=duration,
            used_live_api=True,
        )

    def _synthetic_fallback(self) -> VoiceTranscriptionResult:
        return VoiceTranscriptionResult(
            transcript=(
                "Traditional handmade Madhubani folk art painting crafted using organic mineral "
                "pigments on handmade paper depicting nature motifs. Handcrafted by rural artisans."
            ),
            language_code="hi",
            duration_seconds=18.5,
            used_live_api=False,
        )
