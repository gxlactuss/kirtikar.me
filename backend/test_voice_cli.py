"""CLI utility to test live Voice-to-Catalog pipeline with Sarvam AI and Gemini 2.0 Flash."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Optional

# Add backend directory and venv site-packages to sys.path so it runs seamlessly anywhere
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

for venv_dir in [backend_dir / ".venv", backend_dir / "venv"]:
    if venv_dir.exists():
        for sp in (venv_dir / "lib").glob("python*/site-packages"):
            if sp.exists() and str(sp) not in sys.path:
                sys.path.insert(0, str(sp))

def _load_env_fallback(env_path: Path):
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if " #" in v:
                    v = v.split(" #", 1)[0].strip()
                v = v.strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v

_load_env_fallback(backend_dir / ".env")

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
from app.services.vision.pipeline import ImageStation
from app.services.voice.pipeline import VoiceStation


def record_microphone(duration_seconds: int = 10) -> Path:
    """Record audio from Linux microphone using arecord."""
    tmp_path = Path(tempfile.gettempdir()) / f"kirtikar_voice_{uuid.uuid4().hex[:8]}.wav"
    print(f"\n🎙️  Recording for {duration_seconds} seconds... SPEAK NOW! (e.g. Hindi, Hinglish)")
    print("---------------------------------------------------------------")
    try:
        cmd = [
            "arecord",
            "-d",
            str(duration_seconds),
            "-f",
            "cd",
            "-t",
            "wav",
            "-r",
            "16000",
            "-c",
            "1",
            str(tmp_path),
        ]
        subprocess.run(cmd, check=True)
        print("✅ Recording complete!")
        return tmp_path
    except Exception as e:
        print(f"❌ arecord error: {e}")
        print("Tip: You can also pass an existing audio file: python test_voice_cli.py --file path/to/audio.wav")
        sys.exit(1)


def run_pipeline(
    audio_path: Path,
    image_path: Optional[Path] = None,
    output_json_path: Optional[Path] = None,
):
    print("\n===============================================================")
    print("🚀 KIRTIKAR MULTIMODAL (IMAGE + VOICE) TO CATALOG TEST")
    print("===============================================================")
    print(f"📁 Audio Input: {audio_path} ({audio_path.stat().st_size} bytes)")
    if image_path:
        print(f"📸 Image Input: {image_path} ({image_path.stat().st_size} bytes)")
    else:
        print("📸 Image Input: None (voice-only mode)")
    print(f"🔑 Sarvam Key : {'Configured' if settings.SARVAM_API_KEY else 'Missing (synthetic fallback)'}")
    print(f"🔑 Gemini Key : {'Configured' if settings.GEMINI_API_KEY else 'Missing (synthetic fallback)'}")
    print(f"🧠 Model      : {settings.GEMINI_MODEL}")
    print("---------------------------------------------------------------")

    listing_uuid = uuid.uuid4()
    item_id = f"item_{str(listing_uuid)[:8]}"

    # 1. Vision Station (if image provided)
    image_station_output = {}
    clean_image_path = None
    if image_path and image_path.exists():
        print("\n[1/5] 📸 Processing Image Station (OpenCV & IS-Net)...")
        img_station = ImageStation()
        out_dir = backend_dir / "generated_assets"
        img_res = img_station.process_image(
            input_path=str(image_path),
            output_dir=str(out_dir),
            item_id=item_id,
        )
        q = img_res.get("quality", {})
        outputs = img_res.get("outputs", {})
        print(f"   • Quality Gate    : {'✅ PASSED' if q.get('passed') else '⚠️ REJECTED'}")
        print(f"   • Blur Score      : {q.get('blur_score'):.1f} (threshold: 100.0)")
        print(f"   • ROI Brightness  : {q.get('roi_brightness_score'):.1f}/255 (range: 55-185)")
        if outputs.get("clean_image"):
            clean_image_path = outputs.get("clean_image")
            print(f"   • Studio Cutout   : {clean_image_path}")
            print(f"   • Mobile Thumbnail: {outputs.get('thumbnail')}")
        image_station_output = img_res
    else:
        print("\n[1/5] 📸 Image Station skipped (no image supplied)")

    # 2. Voice Station
    print("\n[2/5] 🎙️ Processing Voice Station (Sarvam AI)...")
    voice_station = VoiceStation()
    voice_res = voice_station.process_audio(audio_path, allow_synthetic_fallback=True)
    print(f"   • Detected Language: {voice_res.language_code.upper()}")
    print(f"   • Duration         : {voice_res.duration_seconds:.1f}s")
    print(f"   • English Speech   : \"{voice_res.transcript}\"")

    # 3. Fact Sheet Station (Gemini Flash Multimodal)
    step_header = "Multimodal Audio + Vision" if image_path else "Audio Transcript"
    print(f"\n[3/5] 🧠 Extracting Modular Sheet (Gemini Flash - {settings.GEMINI_MODEL}) [{step_header}]...")
    extractor = GeminiExtractor()
    extraction = extractor.extract_fact_sheet(
        transcript=voice_res.transcript,
        detected_language=voice_res.language_code,
        image_path=str(image_path) if image_path else None,
        allow_synthetic_fallback=True,
    )
    print(f"   • Title      : {extraction.title}")
    print(f"   • Craft Type : {extraction.craft_type}")
    print(f"   • Material   : {extraction.material}")
    print(f"   • Dimensions : {extraction.dimensions or 'Not specified'}")
    print(f"   • Origin     : {extraction.origin or 'India'}")
    print(f"   • Colors     : {', '.join(extraction.colors) if extraction.colors else 'None'}")
    print(f"   • Story      : \"{extraction.story_summary}\"")
    if extraction.missing_fields:
        print(f"   ⚠️ Missing in Speech: {', '.join(extraction.missing_fields)}")

    # 4. Price Advisor
    print("\n[4/5] 🏷️ Running Price Advisor Stage...")
    ctx = PipelineContext(listing_id=listing_uuid)
    ctx.fact_sheet_output = FactSheetOutput(
        title=extraction.title,
        craft_type=extraction.craft_type,
        material=extraction.material,
        story_summary=extraction.story_summary,
        attributes=extraction.attributes,
    )
    PriceStage().run(ctx)
    pr: PriceStageOutput = ctx.price_output
    print(f"   • Recommended Price: ₹ {pr.recommended_price:.2f} {pr.currency}")
    print(f"   • Fair Market Range: ₹ {pr.min_price:.2f} - ₹ {pr.max_price:.2f}")

    # 5. Multi-Channel Syndication
    print("\n[5/5] 🌐 Multi-Channel Syndication Adapters...")
    media_url = clean_image_path or "https://images.unsplash.com/photo-1579783900882-c0d3dad7b119?w=800"
    canonical = CanonicalListing(
        id=str(ctx.listing_id),
        title=extraction.title,
        description=extraction.story_summary,
        price=pr.recommended_price,
        currency=pr.currency,
        category=extraction.craft_type,
        materials=[extraction.material],
        dimensions=extraction.dimensions,
        media_urls=[media_url],
        attributes=extraction.attributes,
    )

    ondc_res = ONDCPublishingAdapter().publish(canonical)
    meta_res = MetaPublishingAdapter().publish(canonical)
    google_res = GoogleMerchantPublishingAdapter().publish(canonical)

    print(f"   ✅ ONDC Beckn Status        : {ondc_res.status} (ID: {ondc_res.external_id})")
    print(f"   ✅ Meta WhatsApp Store      : {meta_res.status} (ID: {meta_res.external_id})")
    print(f"   ✅ Google Merchant Center   : {google_res.status} (ID: {google_res.external_id})")

    # App JSON Format (matches Flutter Listing and FactSheet models)
    price_in_paise = int(round(pr.recommended_price * 100))
    price_floor_in_paise = int(round(pr.min_price * 100))
    suggested_price_in_paise = int(round(pr.recommended_price * 100))
    material_cost_in_paise = int(round(pr.min_price * 0.35 * 100))

    missing = extraction.missing_fields or []
    follow_up_question = None
    suggestions = []

    clean_dimensions = extraction.dimensions
    if isinstance(clean_dimensions, str) and clean_dimensions.strip().lower() in ("null", "none", "n/a", "not specified", "not mentioned", "unknown"):
        clean_dimensions = None

    if "dimensions" in missing or not clean_dimensions:
        follow_up_question = "Could you tell us the approximate size or height of this craft?"
        suggestions.append({
            "id": "sug_size",
            "spokenPrompt": "Would you like to specify the size as Medium?",
            "textIfAccepted": "Size: Medium",
            "accepted": None,
        })

    if extraction.stated_price is None:
        suggestions.append({
            "id": "sug_price",
            "spokenPrompt": f"Would you like to set the listing price to ₹{int(round(pr.recommended_price))}?",
            "textIfAccepted": f"₹{int(round(pr.recommended_price))}",
            "accepted": None,
        })

    app_status = "needsAttention" if follow_up_question else "ready"

    app_listing = {
        "id": str(ctx.listing_id),
        "status": app_status,
        "title": extraction.title,
        "description": extraction.story_summary,
        "imageUrls": [media_url],
        "suggestedPriceInPaise": suggested_price_in_paise,
        "priceFloorInPaise": price_floor_in_paise,
        "previewUrl": f"https://kirtikar.app/preview/{str(ctx.listing_id)[:8]}",
        "photoConsent": True,
        "storyConsent": True,
        "views": 0,
        "templateListingId": None,
        "followUpQuestion": follow_up_question,
        "factSheet": {
            "material": extraction.material,
            "size": clean_dimensions or "Medium (8x6 inches)",
            "colour": ", ".join(extraction.colors) if extraction.colors else "Terracotta / Earthy Red",
            "technique": extraction.craft_type,
            "quantity": 1,
            "priceInPaise": price_in_paise,
            "hoursToMake": 4.0,
            "materialCostInPaise": material_cost_in_paise,
            "isOneOfAKind": False,
        },
        "suggestions": suggestions,
    }

    # Generate complete structured JSON output
    catalog_json = {
        "app_format": app_listing,
        "listing_id": str(ctx.listing_id),
        "inputs": {
            "audio_path": str(audio_path),
            "audio_bytes": audio_path.stat().st_size,
            "image_path": str(image_path) if image_path else None,
        },
        "voice_station": {
            "detected_language": voice_res.language_code,
            "duration_seconds": voice_res.duration_seconds,
            "english_speech": voice_res.transcript,
        },
        "image_station": image_station_output,
        "modular_sheet": {
            "title": extraction.title,
            "craft_type": extraction.craft_type,
            "material": extraction.material,
            "dimensions": extraction.dimensions,
            "origin": extraction.origin,
            "colors": extraction.colors,
            "story_summary": extraction.story_summary,
            "stated_price": extraction.stated_price,
            "missing_fields": extraction.missing_fields,
            "attributes": extraction.attributes,
        },
        "pricing": {
            "stated_price": extraction.stated_price,
            "recommended_price": pr.recommended_price,
            "fair_market_min": pr.min_price,
            "fair_market_max": pr.max_price,
            "currency": pr.currency,
        },
        "syndication": {
            "ondc": {
                "channel": ondc_res.channel,
                "status": ondc_res.status,
                "external_id": ondc_res.external_id,
                "details": ondc_res.details,
            },
            "meta_whatsapp": {
                "channel": meta_res.channel,
                "status": meta_res.status,
                "external_id": meta_res.external_id,
                "details": meta_res.details,
            },
            "google_merchant": {
                "channel": google_res.channel,
                "status": google_res.status,
                "external_id": google_res.external_id,
                "details": google_res.details,
            },
        },
    }

    print("\n---------------------------------------------------------------")
    print("📱 Kirtikar Mobile App Model Preview:")
    print(f"   Listing ID    : {app_listing['id']}")
    print(f"   Status        : {app_listing['status']}")
    print(f"   Title         : {app_listing['title']}")
    print(f"   Price (Paise) : {app_listing['suggestedPriceInPaise']} (₹{app_listing['suggestedPriceInPaise']/100:.2f})")
    print(f"   Material      : {app_listing['factSheet']['material']}")
    print(f"   Follow-up Q   : {app_listing['followUpQuestion'] or 'None (Fully Specified)'}")
    print("===============================================================\n")

    if output_json_path:
        out_path = Path(output_json_path)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(catalog_json, f, indent=2, ensure_ascii=False)
        print(f"💾 Catalog JSON (with app_format) saved successfully to: {out_path.resolve()}")

    return catalog_json


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Kirtikar Multimodal Voice+Vision Pipeline")
    parser.add_argument("--file", type=str, help="Path to an existing audio file (.wav, .mp3, .m4a)")
    parser.add_argument("--image", "-i", type=str, help="Path to a craft photograph (.jpg, .png)")
    parser.add_argument("--record", action="store_true", help="Record audio directly from microphone")
    parser.add_argument("--seconds", type=int, default=8, help="Duration to record in seconds (default: 8)")
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="listing_output.json",
        help="Path to save the generated catalog JSON (default: listing_output.json)",
    )
    args = parser.parse_args()

    audio_file = None
    should_cleanup = False

    if args.file:
        audio_file = Path(args.file)
        if not audio_file.exists():
            print(f"❌ Audio file not found: {audio_file}")
            sys.exit(1)
    elif args.record:
        audio_file = record_microphone(args.seconds)
        should_cleanup = True
    else:
        print("Select an option:")
        print("  1) Record live voice from microphone (8 seconds)")
        print("  2) Test with built-in sample craft voice note")
        choice = input("Enter choice (1 or 2, default 1): ").strip()

        if choice == "2":
            tmp_path = Path(tempfile.gettempdir()) / "sample_craft.wav"
            tmp_path.write_bytes(b"RIFF" + b"\x00" * 40)
            audio_file = tmp_path
            should_cleanup = True
        else:
            audio_file = record_microphone(args.seconds)
            should_cleanup = True

    image_file = None
    if args.image:
        image_file = Path(args.image)
        if not image_file.exists():
            print(f"❌ Image file not found: {image_file}")
            sys.exit(1)

    try:
        run_pipeline(
            audio_path=audio_file,
            image_path=image_file,
            output_json_path=Path(args.output),
        )
    finally:
        if should_cleanup and audio_file and audio_file.exists():
            audio_file.unlink()
