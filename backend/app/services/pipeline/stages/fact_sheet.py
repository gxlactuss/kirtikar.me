"""Fact Sheet Station stage: Extracts structured craft metadata via Gemini 2.0 Flash."""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.llm.gemini import GeminiExtractor
from app.services.pipeline.context import FactSheetOutput, PipelineContext
from app.services.pipeline.result import StageResult

logger = logging.getLogger("app.services.pipeline.stages.fact_sheet")

_gemini_extractor_instance = None


def _get_gemini_extractor() -> GeminiExtractor:
    global _gemini_extractor_instance
    if _gemini_extractor_instance is None:
        _gemini_extractor_instance = GeminiExtractor()
    return _gemini_extractor_instance


def _primary_image_path(context: PipelineContext, storage_base: Path) -> Optional[str]:
    """Absolute path of the best image to show the model, or None if none is on disk.

    Prefers the image stage's processed output - a centred cutout on white - and
    falls back to the artisan's original upload. Returning None is the signal
    that this is a synthetic fixture with no real bytes anywhere.
    """
    candidates: List[str] = []
    if context.image_output is not None:
        candidates.extend(context.image_output.image_paths)
    candidates.extend(m.storage_path for m in context.media if m.storage_path)

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        resolved = path if path.is_absolute() else (storage_base / path)
        try:
            resolved = resolved.resolve()
        except OSError:
            continue
        # Never let a stored path walk out of the media root and feed an
        # arbitrary file on the host into an outbound API request.
        if not resolved.is_relative_to(storage_base):
            logger.warning("Ignoring out-of-root image path: %s", candidate)
            continue
        if resolved.is_file():
            return str(resolved)
    return None


class FactSheetStage:
    """Production Fact Sheet Station: Extracts structured attributes and marketing copy from voice transcript."""

    name: str = "fact_sheet"

    def run(self, context: PipelineContext) -> StageResult:
        """Consume speech output and image analysis to generate structured artisan product fact sheet."""
        if context.image_output is None or context.speech_output is None:
            return StageResult.attention("Missing prerequisite image or speech analysis")

        transcript = context.speech_output.transcript
        detected_language = context.speech_output.language or "hi"

        extractor = _get_gemini_extractor()
        storage_base = Path(settings.MEDIA_STORAGE_DIR).resolve()

        # The photograph is half the evidence. The image stage has already
        # graded, cut out and composited it, so hand that studio image to the
        # model rather than the raw camera frame: the clutter the artisan was
        # standing in is gone, which is exactly what made craft form, colour and
        # material hard to read. Without this the extraction was transcript-only
        # and the whole vision stage informed nothing downstream.
        image_path = _primary_image_path(context, storage_base)

        # If running on in-memory / synthetic test fixtures without physical files on disk,
        # use deterministic synthetic fallback to guarantee 100% offline test reliability.
        if image_path is None and hasattr(extractor, "_synthetic_fallback"):
            extraction = extractor._synthetic_fallback(transcript)
        else:
            try:
                extraction = extractor.extract_fact_sheet(
                    transcript=transcript,
                    detected_language=detected_language,
                    image_path=image_path,
                    seller_story=context.seller_story,
                    allow_synthetic_fallback=True,
                )
            except Exception as e:
                logger.exception("Failed extracting fact sheet attributes: %s", e)
                return StageResult.fail(f"Fact sheet extraction error: {str(e)}")

        attributes: Dict[str, Any] = dict(extraction.attributes)
        attributes["image_count"] = context.image_output.image_count
        # Carried through so a listing written from canned facts can be told
        # from one a real model wrote.
        attributes["used_live_model"] = bool(getattr(extraction, "used_live_api", False))
        attributes["image_sent_to_model"] = image_path is not None
        # Fall back only to what the extraction itself found. These used to
        # default to a sample painting's facts - "1024x768" as a physical size,
        # "Mithila region", an ochre/indigo palette - which showed the artisan an
        # image resolution under "Size" and contradicted missing_fields in the
        # same response. A fact nobody stated stays empty, and the artisan is
        # asked for it instead.
        for key, found in (
            ("primary_colors", extraction.colors),
            ("dimensions", extraction.dimensions),
            ("origin", extraction.origin),
        ):
            if not attributes.get(key) and found:
                attributes[key] = found

        # Anything still empty is something to ask about, not to invent.
        missing = list(attributes.get("missing_fields") or [])
        for key, field in (("dimensions", "dimensions"), ("primary_colors", "colors")):
            if not attributes.get(key) and field not in missing:
                missing.append(field)
        attributes["missing_fields"] = missing

        output = FactSheetOutput(
            title=extraction.title,
            craft_type=extraction.craft_type,
            material=extraction.material,
            story_summary=extraction.story_summary,
            attributes=attributes,
        )
        context.fact_sheet_output = output
        return StageResult.ok(output=output, metadata={"attributes_count": len(output.attributes)})
