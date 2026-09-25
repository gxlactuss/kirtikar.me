"""Gemini 2.0 Flash service for structured catalog extraction."""
import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("app.services.llm.gemini")

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# Gemini rejects an inline image whose declared mime type does not match its
# bytes, so the extension has to map to the real type. Phone cameras hand us
# HEIC and WebP as often as JPEG, and labelling those "image/jpeg" was enough
# to lose the photograph from the request.
_IMAGE_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".gif": "image/gif",
}
DEFAULT_IMAGE_MIME_TYPE = "image/jpeg"

# Transient refusals: the request was fine, the service was not.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def image_mime_type(path: str) -> str:
    """Map a file extension to the mime type Gemini should be told to expect."""
    return _IMAGE_MIME_TYPES.get(os.path.splitext(path)[1].lower(), DEFAULT_IMAGE_MIME_TYPE)


@dataclass(frozen=True)
class GeminiExtractionResult:
    title: str
    craft_type: str
    material: str
    story_summary: str
    stated_price: Optional[float] = None
    dimensions: Optional[str] = None
    origin: Optional[str] = None
    colors: List[str] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    # False when these facts are the canned fallback rather than a real
    # extraction, so callers can tell a working demo from a silent failure.
    used_live_api: bool = False


EXTRACTION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "title": {
            "type": "STRING",
            "description": "Descriptive, high-converting English product title",
        },
        "craft_type": {
            "type": "STRING",
            "description": "Traditional Indian craft form (e.g. Madhubani Art, Terracotta Pottery, Dhokra, Chanderi)",
        },
        "material": {
            "type": "STRING",
            "description": "Primary authentic raw materials mentioned (e.g. Natural river clay, handmade paper)",
        },
        "story_summary": {
            "type": "STRING",
            "description": "Artisan personal backstory, tradition, cultural significance, and making technique",
        },
        "stated_price": {
            "type": "NUMBER",
            "description": "Numeric price in INR if explicitly stated by artisan. Null if not mentioned.",
        },
        "dimensions": {
            "type": "STRING",
            "description": "Product dimensions or size if mentioned. Null if not mentioned.",
        },
        "origin": {
            "type": "STRING",
            "description": "Geographical region or craft cluster of origin if mentioned.",
        },
        "colors": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Dominant colors mentioned.",
        },
        "missing_fields": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Key commercial fields missing from audio note (e.g. ['price', 'dimensions'])",
        },
    },
    "required": ["title", "craft_type", "material", "story_summary"],
}

SYSTEM_INSTRUCTION = """You are an expert Indian Handicrafts Cataloging Assistant for Kirtikar (SIH-090).
Your job is to take an artisan's spoken voice note (translated to English) and optional product photograph to extract structured product metadata for e-commerce publishing.

RULES:
1. Extract authentic craft facts directly from the transcript and visual cues from the attached photograph.
2. NEVER hallucinate or invent a price or dimensions if the artisan did not explicitly state them.
3. If price is not mentioned, set `stated_price` to null and add 'price' to `missing_fields`.
4. If dimensions/size are not mentioned, set `dimensions` to null and add 'dimensions' to `missing_fields`.
5. Preserve authentic Indian craft terminology (e.g., Madhubani, Warli, Terracotta Pottery, Zari, Pattachitra, Blue Pottery).
6. Craft a compelling artisan story summary highlighting their traditional heritage, craft technique, and craftsmanship.
7. If an image is provided, examine it closely to confirm craft form, natural colors, visible textures, and authentic material composition.

ABOUT THE ARTISAN'S OWN STORY:
If the artisan's profile story is supplied, it is background about the maker, not
about this particular piece. Use it for at most ONE short clause in
`story_summary` - the kind of detail a buyer remembers, such as how long they
have practised, who taught them, or where they work. Rules:
- Never retell the story or quote it at length. One clause, woven into a
  sentence about the product. The piece stays the subject.
- Only use it when it genuinely fits this craft. If the story is about weaving
  and this is a clay pot, leave it out entirely.
- Never turn it into a fact about the product. It must not change craft_type,
  material, dimensions, price, colors or origin, all of which come only from the
  voice note and the photograph.
- Never invent detail that is not in the story.
"""


class GeminiExtractor:
    """Production LLM Extractor using Gemini 2.0 Flash with Structured Outputs."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_attempts: int = 2,
        retry_backoff_seconds: float = 1.5,
        fallback_models: Optional[List[str]] = None,
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        # A multimodal extraction on the preferred Flash model measures around
        # 25s, so the old 30s ceiling was tripping its own read timeout on
        # perfectly healthy calls.
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(settings.GEMINI_TIMEOUT_SECONDS)
        )
        self.max_attempts = max(1, max_attempts)
        self.retry_backoff_seconds = retry_backoff_seconds
        self.fallback_models = (
            fallback_models
            if fallback_models is not None
            else settings.gemini_fallback_models
        )

    def extract_fact_sheet(
        self,
        transcript: str,
        detected_language: str = "hi",
        image_path: Optional[str] = None,
        seller_story: Optional[str] = None,
        allow_synthetic_fallback: bool = True,
    ) -> GeminiExtractionResult:
        """Extract structured catalog attributes from transcript and optional craft photo.

        `seller_story` is the artisan's own profile story, written once and reused
        across their listings. It is background colour for the description only:
        the prompt allows a single clause from it and forbids it from touching any
        product fact.
        """
        if not transcript or not transcript.strip():
            raise ValueError("Cannot extract from empty transcript")

        if self.api_key:
            last_error: Optional[BaseException] = None

            # Work down the model chain. The preferred Flash model is the most
            # capable but also the busiest, and a listing written from canned
            # facts is worse than one written by a lighter model, so exhaust
            # every real model before falling back to synthetic output.
            chain = self._model_chain()
            for model_index, model_name in enumerate(chain):
                # An overloaded model answers its 503 slowly, measured at around
                # 45s on the shared Flash tier, so retrying it where a spare
                # exists spent a minute and a half before the spare was even
                # asked. Only the last model in the chain gets a second try.
                attempts_here = self.max_attempts if model_index == len(chain) - 1 else 1
                for attempt in range(attempts_here):
                    last_attempt = attempt == attempts_here - 1
                    try:
                        return self._call_gemini_api(
                            transcript,
                            detected_language,
                            image_path=image_path,
                            seller_story=seller_story,
                            model_name=model_name,
                        )
                    except httpx.HTTPStatusError as e:
                        last_error = e
                        status = e.response.status_code
                        # 503 and 429 are routine on the shared Flash tier; the
                        # first live call of a session commonly draws one.
                        if status in _RETRYABLE_STATUS and not last_attempt:
                            delay = self.retry_backoff_seconds * (2 ** attempt)
                            logger.info(
                                "Gemini model %s returned %s, retrying in %.1fs (attempt %d/%d)",
                                model_name, status, delay, attempt + 1, attempts_here,
                            )
                            time.sleep(delay)
                            continue
                        logger.warning(
                            "Gemini model %s HTTP error %s: %s",
                            model_name, status, e.response.text[:500],
                        )
                        break
                    except (httpx.TimeoutException, httpx.TransportError) as e:
                        # A dropped connection says nothing about the request,
                        # so it is worth the same second chance as a 503.
                        last_error = e
                        if not last_attempt:
                            delay = self.retry_backoff_seconds * (2 ** attempt)
                            logger.info(
                                "Gemini model %s transport error (%s), retrying in %.1fs",
                                model_name, e, delay,
                            )
                            time.sleep(delay)
                            continue
                        logger.warning(
                            "Gemini model %s unreachable after %d attempts: %s",
                            model_name, attempts_here, e,
                        )
                        break
                    except Exception as e:
                        # A malformed response or a bad request will not fix
                        # itself on a retry, so move to the next model.
                        last_error = e
                        logger.warning("Gemini model %s call failed: %s", model_name, e)
                        break

                if len(chain) > 1:
                    logger.info("Falling through to the next Gemini model after %s", model_name)

            if allow_synthetic_fallback:
                logger.info("Falling back to synthetic extraction after Gemini API failure")
                return self._synthetic_fallback(transcript, image_path=image_path)
            if last_error is not None:
                raise last_error
            raise RuntimeError("Gemini extraction failed for every configured model")

        if allow_synthetic_fallback:
            return self._synthetic_fallback(transcript, image_path=image_path)

        raise RuntimeError("Gemini API key is missing and synthetic fallback is disabled")

    def _model_chain(self) -> List[str]:
        """The configured model first, then the declared fallbacks, deduplicated."""
        chain = [self.model_name] + list(self.fallback_models)
        seen, ordered = set(), []
        for name in chain:
            if name and name not in seen:
                seen.add(name)
                ordered.append(name)
        return ordered

    def _call_gemini_api(
        self,
        transcript: str,
        detected_language: str,
        image_path: Optional[str] = None,
        seller_story: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> GeminiExtractionResult:
        # The key travels in a header, never in the query string: httpx logs the
        # full URL at INFO level, which wrote the secret into the server log on
        # every extraction.
        endpoint = f"{GEMINI_API_BASE_URL}/{model_name or self.model_name}:generateContent"

        parts = []
        if image_path and os.path.exists(image_path):
            try:
                with open(image_path, "rb") as img_f:
                    img_bytes = img_f.read()
                mime_type = image_mime_type(image_path)
                parts.append({
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": base64.b64encode(img_bytes).decode("utf-8"),
                    }
                })
            except Exception as img_err:
                logger.warning("Failed to attach image to Gemini payload: %s", img_err)

        prompt_text = f"Artisan Voice Note Transcript (detected language: {detected_language}):\n\n\"{transcript}\""
        if image_path and os.path.exists(image_path):
            prompt_text += "\n\nNote: The artisan also provided the attached craft photograph. Combine visual evidence from the image (craft style, colors, visible texture, materials, shape) with the artisan's voice note to construct the most accurate, compelling fact sheet."

        story = (seller_story or "").strip()
        if story:
            # Capped so a long profile story cannot crowd out the voice note, which
            # is the only source of truth about this particular piece.
            if len(story) > 600:
                story = story[:600].rsplit(" ", 1)[0] + "…"
            prompt_text += (
                "\n\nThe artisan's profile story (background about the maker, not "
                f"about this piece):\n\"{story}\"\n"
                "Follow the system instruction: at most one short clause from this "
                "may appear in story_summary, and only if it genuinely fits this "
                "craft. It must not change any product fact."
            )

        parts.append({"text": prompt_text})

        payload = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_INSTRUCTION}],
            },
            "contents": [
                {
                    "parts": parts
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "response_schema": EXTRACTION_SCHEMA,
                "temperature": 0.2,
            },
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                endpoint,
                json=payload,
                headers={"x-goog-api-key": self.api_key or ""},
            )
            response.raise_for_status()
            data = response.json()

        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned no candidates")

        content_parts = candidates[0].get("content", {}).get("parts", [])
        if not content_parts:
            raise ValueError("Gemini returned empty content parts")

        raw_json_str = content_parts[0].get("text", "{}")
        parsed = json.loads(raw_json_str)

        stated_price = parsed.get("stated_price")
        if stated_price is not None:
            stated_price = float(stated_price)

        dimensions = parsed.get("dimensions")
        if isinstance(dimensions, str) and dimensions.strip().lower() in ("null", "none", "n/a", "not specified", "not mentioned", "unknown"):
            dimensions = None

        origin = parsed.get("origin")
        if isinstance(origin, str) and origin.strip().lower() in ("null", "none", "n/a", "not specified", "not mentioned", "unknown"):
            origin = None

        colors = parsed.get("colors") or []
        missing_fields = parsed.get("missing_fields") or []

        if dimensions is None and "dimensions" not in missing_fields:
            missing_fields.append("dimensions")
        if stated_price is None and "price" not in missing_fields:
            missing_fields.append("price")

        attributes = {
            "origin": origin,
            "dimensions": dimensions,
            "primary_colors": colors,
            "stated_price": stated_price,
            "missing_fields": missing_fields,
        }

        return GeminiExtractionResult(
            title=parsed.get("title", "Handcrafted Artisan Product"),
            craft_type=parsed.get("craft_type", "Traditional Handicraft"),
            material=parsed.get("material", "Natural indigenous materials"),
            story_summary=parsed.get("story_summary", transcript),
            stated_price=stated_price,
            dimensions=dimensions,
            origin=origin,
            colors=colors,
            missing_fields=missing_fields,
            attributes=attributes,
            used_live_api=True,
        )

    def _synthetic_fallback(self, transcript: str, image_path: Optional[str] = None) -> GeminiExtractionResult:
        """What to show when no model could be reached: the artisan's own words, and nothing invented.

        This used to answer with a fixed Madhubani painting from the Mithila
        region (or, for a path containing "pottery", a Khurja water pot), so a
        live run whose writing model was down described some other object with
        total confidence. The site already labels this case as the offline
        fallback; the least it can do is not contradict the photo. Every fact
        nobody stated is left empty and listed as missing, so the review screens
        ask for it instead.
        """
        missing = ["price", "dimensions", "colors", "material"]
        return GeminiExtractionResult(
            title="Handmade item",
            craft_type="Handcraft",
            material="",
            story_summary=transcript,
            stated_price=None,
            dimensions=None,
            origin=None,
            colors=[],
            missing_fields=list(missing),
            attributes={
                "dimensions": None,
                "origin": None,
                "primary_colors": [],
                "stated_price": None,
                "missing_fields": list(missing),
            },
        )
