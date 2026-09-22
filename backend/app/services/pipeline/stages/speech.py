"""Voice Station stage: Transcribes and translates artisan audio notes."""
import logging
from pathlib import Path

from app.core.config import settings
from app.schemas.enums import MediaType
from app.services.pipeline.context import PipelineContext, SpeechStageOutput
from app.services.pipeline.result import StageResult
from app.services.voice.pipeline import NoSpeechError, VoiceServiceError, VoiceStation

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
        typed = (context.typed_description or "").strip()

        # A recording that is really on disk is transcribed live or not at all.
        # It used to fall back to a canned transcript about a Madhubani
        # painting whenever Sarvam failed, so an artisan who talked about a
        # clay pot got a painting's listing and no sign that nothing was heard.
        # Only a fixture with no bytes behind it (the in-memory test suite)
        # still gets the canned text, the same split the image stage makes.
        live = raw_path.exists()
        try:
            result = station.process_audio(raw_path, allow_synthetic_fallback=not live)
        except NoSpeechError:
            if typed:
                return self._typed(context, typed, reason="no words in the recording")
            # Asking again is the only fix, so there is nothing to retry.
            return StageResult.attention(
                "We could not hear any words in the voice note. Please record it "
                "again, a little closer to the phone, and describe the item."
            )
        except VoiceServiceError as e:
            if typed:
                return self._typed(context, typed, reason=str(e))
            # Failure rather than attention: a busy or unreachable service is
            # worth the runner's retry. If that fails too, this sentence is what
            # the artisan is shown.
            return StageResult.fail(str(e))
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
        return StageResult.ok(
            output=output,
            metadata={
                "detected_language": result.language_code,
                "used_live_api": result.used_live_api,
            },
        )

    def _typed(self, context: PipelineContext, typed: str, reason: str) -> StageResult:
        """Use what the artisan typed when the recording could not be used."""
        output = SpeechStageOutput(
            audio_path="",
            transcript=typed,
            language=context.seller_language or "hi",
            duration_seconds=0.0,
        )
        context.speech_output = output
        logger.info(
            "Listing %s -> voice note unusable (%s); using the typed description",
            context.listing_id,
            reason,
        )
        return StageResult.ok(output=output, metadata={"source": "typed", "voice_error": reason})
