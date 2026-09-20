"""Applying artisan-supplied values to a listing's fact sheet.

The app names fields the way its own `ListingField` enum does. This is the one
place that maps those names onto `ListingResult` columns and coerces the value,
so the correction endpoint and the answer endpoint cannot drift apart.
"""
from typing import Any, Callable, Dict, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.listing import Listing
from app.models.listing_result import ListingResult
from app.models.suggestion import Suggestion


def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("expected a number, got a boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    return int(text)  # raises ValueError, caught by the caller


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    raise ValueError("expected a boolean")


# app field name -> (ListingResult column, coercion)
FIELD_COLUMNS: Dict[str, Tuple[str, Callable[[Any], Any]]] = {
    "material": ("material", _as_text),
    "size": ("size", _as_text),
    "colour": ("colour", _as_text),
    "technique": ("technique", _as_text),
    "origin": ("origin", _as_text),
    "quantity": ("quantity", _as_int),
    # The app sends money in paise, never rupees, so it never rides on a float.
    "price": ("price_in_paise", _as_int),
    "isOneOfAKind": ("is_one_of_a_kind", _as_bool),
}


def result_for(db: Session, listing: Listing) -> ListingResult:
    """The listing's result row, created empty if the pipeline never made one."""
    result = listing.result
    if result is None:
        result = ListingResult(listing_id=listing.id)
        db.add(result)
        listing.result = result
    return result


def apply_field_values(
    db: Session, listing: Listing, changes: Dict[str, Any]
) -> ListingResult:
    """Write `changes` onto the listing's fact sheet.

    A name this cannot store is refused rather than dropped: the app shows the
    artisan their answer as saved, so quietly discarding one would lie to them.
    """
    unknown = [name for name in changes if name not in FIELD_COLUMNS]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot store these fields: {', '.join(sorted(unknown))}.",
        )

    result = result_for(db, listing)
    for name, raw in changes.items():
        column, coerce = FIELD_COLUMNS[name]
        try:
            setattr(result, column, coerce(raw))
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Value for '{name}' is not in a form this field can hold.",
            )
    return result


def settle_suggestion_for_field(
    db: Session, listing: Listing, field: str, approved: bool = True
) -> None:
    """Mark the open suggestion about `field` as answered.

    Suggestions record the fact sheet field name in `value`, so that is what the
    app's field name matches. Without this the same gap is asked again on the
    next review, after the artisan has already filled it in.
    """
    for suggestion in listing.suggestions:
        if suggestion.approved is None and (
            suggestion.value == field or suggestion.field == field
        ):
            suggestion.approved = approved
            db.add(suggestion)
