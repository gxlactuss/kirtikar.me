"""Voice Station: Audio pre-processing and Indic speech translation via Sarvam AI."""
import io
import logging
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("app.services.voice.pipeline")

# saaras:v3 is served only from /speech-to-text with mode=translate. The older
# /speech-to-text-translate endpoint tops out at saaras:v2.5 and rejects v3
# outright, and because that rejection was caught and papered over with the
# canned transcript below, every real voice note was being thrown away.
SARVAM_API_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_MODEL = "saaras:v3"

# The synchronous REST call takes audio "under 30 seconds". The site's recorder
# stops itself at 30s, which lands a few frames over, so trim a hair under the
# limit rather than lose the whole note to a 400 over its last 100ms.
_MAX_REST_SECONDS = 29.5

# 429 and 5xx from a shared speech API are routine and pass within seconds.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class NoSpeechError(ValueError):
    """The service answered, but heard no words in the recording."""


class VoiceServiceError(RuntimeError):
    """The speech service could not be used. The message is safe to show."""


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

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout_seconds: float = 30.0,
        max_attempts: int = 2,
        retry_backoff_seconds: float = 1.5,
    ):
        self.api_key = api_key or settings.SARVAM_API_KEY
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)
        self.retry_backoff_seconds = retry_backoff_seconds

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
            except Exception as e:
                logger.warning("Sarvam AI STT API call failed: %s", e)
                if allow_synthetic_fallback:
                    logger.info("Falling back to synthetic transcription after API failure")
                    return self._synthetic_fallback()
                raise

        # No API key provided: use fallback
        if allow_synthetic_fallback:
            return self._synthetic_fallback()

        logger.error("SARVAM_API_KEY is not set; cannot transcribe a real voice note")
        raise VoiceServiceError("Voice notes cannot be transcribed on this server right now.")

    def _call_sarvam_api(self, audio_path: Path) -> VoiceTranscriptionResult:
        """One translated transcript from Sarvam, retrying briefly on transient errors.

        Raises NoSpeechError when the recording holds no words, and
        VoiceServiceError (with a message fit for the artisan) when the service
        itself could not be used.
        """
        headers = {"api-subscription-key": self.api_key}
        audio_bytes, content_type, duration = _prepare_audio(audio_path)
        data = {
            "model": SARVAM_MODEL,
            # Speech in any Indian language in, English text out: the fact
            # sheet and every marketplace listing downstream are English.
            "mode": "translate",
            # Artisans speak whatever they speak; let the model identify it.
            "language_code": "unknown",
        }

        last_error: Optional[BaseException] = None
        for attempt in range(self.max_attempts):
            last_attempt = attempt == self.max_attempts - 1
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(
                        SARVAM_API_URL,
                        headers=headers,
                        files={"file": (audio_path.name, audio_bytes, content_type)},
                        data=data,
                    )
                response.raise_for_status()
                payload = response.json()
                break
            except httpx.HTTPStatusError as e:
                last_error = e
                status = e.response.status_code
                logger.warning("Sarvam STT HTTP %s: %s", status, e.response.text[:500])
                if status in _RETRYABLE_STATUS and not last_attempt:
                    time.sleep(self.retry_backoff_seconds * (2 ** attempt))
                    continue
                raise VoiceServiceError(_describe_http_failure(status)) from e
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_error = e
                logger.warning("Sarvam STT unreachable (attempt %d): %s", attempt + 1, e)
                if not last_attempt:
                    time.sleep(self.retry_backoff_seconds * (2 ** attempt))
                    continue
                raise VoiceServiceError(
                    "The speech service did not answer in time. Please try again."
                ) from e
            except ValueError as e:
                raise VoiceServiceError("The speech service sent back an unreadable answer.") from e
        else:  # pragma: no cover - every path above breaks or raises
            raise VoiceServiceError("The speech service could not be reached.") from last_error

        transcript = (payload.get("transcript") or "").strip()
        if not transcript:
            raise NoSpeechError("Sarvam AI returned empty transcript")

        return VoiceTranscriptionResult(
            transcript=transcript,
            language_code=payload.get("language_code") or "unknown",
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


def _describe_http_failure(status: int) -> str:
    if status in (401, 403):
        return "The speech service rejected the server's key."
    if status == 429:
        return "The speech service is busy right now. Please try again in a minute."
    if status >= 500:
        return "The speech service is having trouble right now. Please try again."
    return "The speech service could not read this recording. Please record it again."


def _prepare_audio(audio_path: Path) -> tuple:
    """The bytes to send, their MIME type, and the recording's length in seconds.

    WAV is what the site records, so it is the case handled exactly: its length
    comes from the header (the new endpoint does not report one), and anything
    past the REST limit is trimmed. Other formats are sent as they are, with a
    length of 0 meaning "not measured".
    """
    ext = audio_path.suffix.lower()
    content_type = {
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".mp4": "audio/mp4",
        ".ogg": "audio/ogg",
        ".webm": "audio/webm",
        ".aac": "audio/aac",
        ".flac": "audio/flac",
    }.get(ext, "audio/wav")
    raw = audio_path.read_bytes()

    if content_type != "audio/wav":
        return raw, content_type, 0.0

    try:
        with wave.open(io.BytesIO(raw)) as src:
            params = src.getparams()
            rate = src.getframerate()
            duration = src.getnframes() / float(rate) if rate else 0.0
            if duration <= _MAX_REST_SECONDS:
                return raw, content_type, round(duration, 2)
            frames = src.readframes(int(_MAX_REST_SECONDS * rate))
    except (wave.Error, EOFError):
        # Not a WAV the stdlib can parse; let the service decide.
        return raw, content_type, 0.0

    out = io.BytesIO()
    with wave.open(out, "wb") as dst:
        dst.setparams(params)
        dst.writeframes(frames)
    logger.info("Trimmed a %.1fs voice note to %.1fs for the REST limit", duration, _MAX_REST_SECONDS)
    return out.getvalue(), content_type, _MAX_REST_SECONDS
