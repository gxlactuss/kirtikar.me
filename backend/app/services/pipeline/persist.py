"""Write a pipeline run's conclusions to the database.

Without this the run was pure computation: stages produced a fact sheet, a price
band and processed images, the runner recorded only the listing's new state, and
every read endpoint answered from hardcoded sample data.
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.listing import Listing
from app.models.listing_result import ListingResult
from app.models.suggestion import Suggestion
from app.services.pipeline.context import PipelineContext

logger = logging.getLogger("app.services.pipeline.persist")

# A handmade piece is one item unless the artisan says otherwise. Leaving this
# null would read as zero stock in the app and show the listing as sold out.
DEFAULT_QUANTITY = 1


def _to_paise(rupees: Optional[float]) -> Optional[int]:
    """Rupees from a stage into paise, which is how money is stored and sent."""
    if rupees is None:
        return None
    try:
        return int(round(float(rupees) * 100))
    except (TypeError, ValueError):
        return None


def _first_text(value: Any) -> Optional[str]:
    """A stage attribute as display text, whether it arrived as a list or scalar."""
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(parts) if parts else None
    text = str(value).strip()
    return text or None


def save_pipeline_result(db: Session, listing: Listing, context: PipelineContext) -> ListingResult:
    """Upsert the run's conclusions for `listing` and replace its suggestions."""
    facts = context.fact_sheet_output
    price = context.price_output
    speech = context.speech_output
    attributes: Dict[str, Any] = dict(facts.attributes) if facts and facts.attributes else {}

    result = listing.result or ListingResult(listing_id=listing.id)

    if facts is not None:
        result.title = facts.title
        result.description = facts.story_summary
        result.material = facts.material
        result.craft_type = facts.craft_type
        result.technique = facts.craft_type
        result.story_summary = facts.story_summary
        result.size = _first_text(attributes.get("dimensions"))
        result.colour = _first_text(attributes.get("primary_colors"))
        result.price_in_paise = _to_paise(attributes.get("stated_price"))

    if price is not None:
        result.suggested_price_in_paise = _to_paise(price.recommended_price)
        result.price_floor_in_paise = _to_paise(price.min_price)
        result.price_ceiling_in_paise = _to_paise(price.max_price)
        # A price the artisan actually said wins over the advisory band.
        if result.price_in_paise is None:
            result.price_in_paise = _to_paise(price.recommended_price)

    if speech is not None:
        result.language = speech.language
        result.transcript = speech.transcript

    if context.confidence_output is not None:
        result.confidence = context.confidence_output.overall_score

    if result.quantity is None:
        result.quantity = DEFAULT_QUANTITY

    result.used_live_model = bool(attributes.get("used_live_model", False))
    result.attributes = attributes
    # A completed run answers whatever it was previously waiting on.
    result.follow_up_question = None

    db.add(result)
    _replace_suggestions(db, listing, attributes)
    db.commit()
    db.refresh(result)
    logger.info("Listing %s -> stored pipeline result '%s'", listing.id, result.title)
    return result


def _replace_suggestions(db: Session, listing: Listing, attributes: Dict[str, Any]) -> None:
    """Turn the fields the run could not fill into things to ask the artisan.

    The artisan is the authority on anything the voice note left out, so a
    missing field becomes a question rather than an invented value.
    """
    missing: List[str] = [str(f) for f in (attributes.get("missing_fields") or [])]

    db.query(Suggestion).filter(Suggestion.listing_id == listing.id).delete(
        synchronize_session=False
    )

    for field in dict.fromkeys(missing):
        prompt = _PROMPTS.get(field)
        if prompt is None:
            continue
        db.add(
            Suggestion(
                listing_id=listing.id,
                field=field,
                value=prompt["value"],
                reason=prompt["reason"],
                approved=None,
            )
        )


_PROMPTS = {
    "price": {
        "value": "price",
        "reason": "The voice note did not mention a price.",
    },
    "dimensions": {
        "value": "size",
        "reason": "The voice note did not mention how big the item is.",
    },
    "colors": {
        "value": "colour",
        "reason": "The voice note did not mention the colour.",
    },
    "origin": {
        "value": "origin",
        "reason": "The voice note did not mention where it was made.",
    },
}


def save_attention_reason(
    db: Session,
    listing: Listing,
    context: PipelineContext,
    reason: Optional[str],
) -> None:
    """Record why a run stopped, so the app can ask the artisan about it.

    A halted run still knows something - the photo was too dark, the item could
    not be separated from its surroundings - and that sentence is the whole
    value of stopping. Anything the earlier stages did manage to work out is
    kept too, rather than discarded with the failure.
    """
    result = listing.result or ListingResult(listing_id=listing.id)

    facts = context.fact_sheet_output
    if facts is not None:
        result.title = result.title or facts.title
        result.description = result.description or facts.story_summary
        result.material = result.material or facts.material
        result.craft_type = result.craft_type or facts.craft_type
        result.technique = result.technique or facts.craft_type

    if context.speech_output is not None:
        result.language = context.speech_output.language
        result.transcript = context.speech_output.transcript

    if result.quantity is None:
        result.quantity = DEFAULT_QUANTITY

    result.follow_up_question = reason
    db.add(result)
    db.commit()
    logger.info("Listing %s -> needs attention: %s", listing.id, reason)
