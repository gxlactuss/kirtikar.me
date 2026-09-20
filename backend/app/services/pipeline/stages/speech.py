"""Voice Station stage: Transcribes and translates artisan audio notes."""
import logging
from pathlib import Path

from app.core.config import settings
from app.schemas.enums import MediaType
from app.services.pipeline.context import PipelineContext, SpeechStageOutput
from app.services.pipeline.result import StageResult
from app.services.voice.pipeline import VoiceStation

logger = logging.getLogger("app.services.pipeline.stages.speech")

_voice_station_instance = None


def _get_voice_station() -> VoiceStation:
    global _voice_station_instance
    if _voice_station_instance is None:
        _voice_station_instance = VoiceStation()
    return _voice_station_instance


class SpeechStage:
    """Production Speech Station: Validates voice note audio and performs Indic translation."""

    name: str = "speech"

    def run(self, context: PipelineContext) -> StageResult:
        audio_media = [m for m in context.media if m.media_type == MediaType.audio]

        if not audio_media:
            # The description step offers a keyboard as well as a microphone.
            # A typed note needs no transcription, so it stands in for the
            # transcript rather than the run stopping for missing audio.
            typed = (context.typed_description or "").strip()
            if typed:
                output = SpeechStageOutput(
                    audio_path="",
                    transcript=typed,
                    language=context.seller_language or "hi",
                    duration_seconds=0.0,
                )
                context.speech_output = output
                logger.info("Listing %s -> using the artisan's typed description", context.listing_id)
                return StageResult.ok(output=output, metadata={"source": "typed"})
            return StageResult.attention("Voice note audio is required")

        primary_audio = audio_media[0]
        subpath = primary_audio.storage_path or f"media/{primary_audio.id}.wav"
        storage_base = Path(settings.MEDIA_STORAGE_DIR).resolve()

        # Path traversal guard
        try:
            raw_path = (storage_base / subpath).resolve()
            if not raw_path.is_relative_to(storage_base):
                logger.error("Path traversal attempt detected in audio path: %s", subpath)
                return StageResult.fail("Invalid media storage path")
        except Exception:
            logger.exception("Failed resolving path for audio media %s", primary_audio.id)
            return StageResult.fail("Invalid media storage path")

        station = _get_voice_station()
        try:
            result = station.process_audio(raw_path, allow_synthetic_fallback=True)
        except ValueError as ve:
            logger.warning("Audio validation failed: %s", ve)
            return StageResult.attention(f"Audio quality error: {str(ve)}")
        except Exception as e:
            logger.exception("Unexpected error processing audio: %s", e)
            return StageResult.fail(f"Audio processing error: {str(e)}")

        output = SpeechStageOutput(
            audio_path=str(raw_path),
            transcript=result.transcript,
            language=result.language_code,
            duration_seconds=result.duration_seconds,
        )
        context.speech_output = output
        return StageResult.ok(output=output, metadata={"detected_language": result.language_code})
