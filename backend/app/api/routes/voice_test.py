"""Interactive voice-to-catalog demo and testing endpoint."""
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
import uuid

from fastapi import APIRouter, File, Form, UploadFile, status

from app.core.config import settings
from app.services.llm.gemini import GeminiExtractor
from app.services.pipeline.context import (
    FactSheetOutput,
    ImageStageOutput,
    PipelineContext,
    PriceStageOutput,
    SpeechStageOutput,
)
from app.services.pipeline.stages.price import PriceStage
from app.services.publishing.base import CanonicalListing
from app.services.publishing.google import GoogleMerchantPublishingAdapter
from app.services.publishing.meta import MetaPublishingAdapter
from app.services.publishing.ondc import ONDCPublishingAdapter
from app.services.voice.pipeline import VoiceStation

router = APIRouter(prefix="/voice", tags=["Voice Demo"])


@router.post(
    "/demo",
    status_code=status.HTTP_200_OK,
    summary="Interactive Voice-to-Catalog Tester",
    description="Upload or speak a voice note and observe the full Sarvam AI -> Gemini 2.0 Flash -> Modular Sheet -> Multi-Channel syndication pipeline.",
)
async def voice_to_catalog_demo(
    file: UploadFile = File(...),
    image: Optional[UploadFile] = File(None),
    seller_story: Optional[str] = Form(None),
    sarvam_key: Optional[str] = Form(None),
    gemini_key: Optional[str] = Form(None),
    model_name: Optional[str] = Form(None),
) -> Dict[str, Any]:
    effective_sarvam_key = sarvam_key or settings.SARVAM_API_KEY
    effective_gemini_key = gemini_key or settings.GEMINI_API_KEY
    effective_model = model_name or settings.GEMINI_MODEL

    # Save audio stream to temporary file
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        tmp_path = Path(tmp_file.name)
        content = await file.read()
        tmp_file.write(content)

    # Save the optional craft photo alongside it. Without this the fact sheet was
    # built from audio alone while the response advertised a multimodal pipeline.
    image_path: Optional[Path] = None
    if image is not None and image.filename:
        image_suffix = Path(image.filename).suffix or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=image_suffix) as tmp_image:
            image_path = Path(tmp_image.name)
            tmp_image.write(await image.read())

    vision_report: Optional[Dict[str, Any]] = None
    gemini_image_path: Optional[Path] = None
    demo_id = uuid.uuid4()

    try:
        # Step 0: Vision Station, so Gemini sees the same studio cutout the
        # marketplace will show rather than the raw camera roll photo.
        if image_path is not None:
            from app.services.vision.pipeline import ImageStation

            # Written under the media root rather than a temp dir: the response
            # reports these paths, so they have to outlive the request.
            vision_dir = Path(settings.MEDIA_STORAGE_DIR).resolve() / "voice_demo" / str(demo_id)
            vision_dir.mkdir(parents=True, exist_ok=True)
            try:
                vision_result = ImageStation().process_image(
                    input_path=str(image_path),
                    output_dir=str(vision_dir),
                    item_id=f"demo_{demo_id.hex[:8]}",
                )
                quality = vision_result.get("quality", {})
                clean_image = vision_result.get("outputs", {}).get("clean_image")
                vision_report = {
                    "quality_passed": quality.get("passed", False),
                    "warnings": quality.get("warnings", []),
                    "blur_score": quality.get("blur_score"),
                    "roi_brightness_score": quality.get("roi_brightness_score"),
                    "outputs": vision_result.get("outputs", {}),
                }
                # A rejected photo produces no cutout, so fall back to the original
                # upload: the artisan still gets a fact sheet plus the retake advice.
                gemini_image_path = Path(clean_image) if clean_image else image_path
            except Exception as exc:  # noqa: BLE001 - demo endpoint stays responsive
                vision_report = {"quality_passed": False, "error": str(exc)}
                gemini_image_path = image_path

        # Step 1: Voice Station (Sarvam AI translation)
        voice_station = VoiceStation(api_key=effective_sarvam_key)
        voice_res = voice_station.process_audio(tmp_path, allow_synthetic_fallback=True)

        # Step 2: Fact Sheet Extraction (Gemini 2.0 Flash)
        gemini_extractor = GeminiExtractor(api_key=effective_gemini_key, model_name=effective_model)
        extraction = gemini_extractor.extract_fact_sheet(
            transcript=voice_res.transcript,
            detected_language=voice_res.language_code,
            image_path=str(gemini_image_path) if gemini_image_path else None,
            seller_story=seller_story,
            allow_synthetic_fallback=True,
        )

        # Step 3: Pricing Advisor Stage
        context = PipelineContext(listing_id=uuid.uuid4())
        context.image_output = ImageStageOutput(
            image_count=1 if gemini_image_path else 0,
            image_paths=[str(gemini_image_path)] if gemini_image_path else [],
            detected_labels=[extraction.craft_type],
            dimensions=[{"width": 1024, "height": 1024}] if gemini_image_path else [],
        )
        context.speech_output = SpeechStageOutput(
            audio_path=str(tmp_path),
            transcript=voice_res.transcript,
            language=voice_res.language_code,
            duration_seconds=voice_res.duration_seconds,
        )
        context.fact_sheet_output = FactSheetOutput(
            title=extraction.title,
            craft_type=extraction.craft_type,
            material=extraction.material,
            story_summary=extraction.story_summary,
            attributes=extraction.attributes,
        )

        price_stage = PriceStage()
        price_res = price_stage.run(context)
        price_output: PriceStageOutput = context.price_output

        # Step 4: Multi-Channel Syndication
        canonical = CanonicalListing(
            id=str(context.listing_id),
            title=extraction.title,
            description=extraction.story_summary,
            price=price_output.recommended_price,
            currency=price_output.currency,
            category=extraction.craft_type,
            materials=[extraction.material],
            dimensions=extraction.dimensions,
            media_urls=[str(gemini_image_path)] if gemini_image_path else [],
            attributes=extraction.attributes,
        )

        ondc_pub = ONDCPublishingAdapter().publish(canonical)
        meta_pub = MetaPublishingAdapter().publish(canonical)
        google_pub = GoogleMerchantPublishingAdapter().publish(canonical)

        return {
            "status": "success",
            "voice_station": {
                "transcript": voice_res.transcript,
                "detected_language": voice_res.language_code,
                "duration_seconds": voice_res.duration_seconds,
                "live_api_used": voice_res.used_live_api,
            },
            "vision_station": vision_report,
            "fact_sheet": {
                "title": extraction.title,
                "craft_type": extraction.craft_type,
                "material": extraction.material,
                "story_summary": extraction.story_summary,
                "stated_price": extraction.stated_price,
                "dimensions": extraction.dimensions,
                "origin": extraction.origin,
                "colors": extraction.colors,
                "missing_fields": extraction.missing_fields,
                "live_api_used": extraction.used_live_api,
                "image_used": gemini_image_path is not None,
                "seller_story_used": bool((seller_story or "").strip()),
                "model": effective_model,
            },
            "pricing": {
                "recommended_price": price_output.recommended_price,
                "min_price": price_output.min_price,
                "max_price": price_output.max_price,
                "currency": price_output.currency,
                "stated_by_artisan": price_res.metadata.get("stated_by_artisan", False),
            },
            "syndication": {
                "ondc": {
                    "channel": ondc_pub.channel,
                    "external_id": ondc_pub.external_id,
                    "status": ondc_pub.status,
                    "details": ondc_pub.details,
                },
                "meta_whatsapp": {
                    "channel": meta_pub.channel,
                    "external_id": meta_pub.external_id,
                    "status": meta_pub.status,
                    "details": meta_pub.details,
                },
                "google_merchant": {
                    "channel": google_pub.channel,
                    "external_id": google_pub.external_id,
                    "status": google_pub.status,
                    "details": google_pub.details,
                },
            },
        }
    finally:
        # The generated studio assets stay on disk for the caller to inspect; only
        # the raw uploads are discarded.
        for path in (tmp_path, image_path):
            if path is not None and path.exists():
                path.unlink()
