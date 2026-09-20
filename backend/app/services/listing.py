"""Listing service managing persistence, ownership verification, and state machine transitions."""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.listing import Listing
from app.schemas.enums import ListingState
from app.services.media_storage import delete_stored_file

# Explicit state transition graph
# queued -> processing -> (needs_attention | ready) -> published
VALID_STATE_TRANSITIONS: Dict[ListingState, Set[ListingState]] = {
    ListingState.queued: {ListingState.processing},
    ListingState.processing: {ListingState.needs_attention, ListingState.ready},
    ListingState.needs_attention: {ListingState.processing, ListingState.ready},
    ListingState.ready: {ListingState.published, ListingState.needs_attention},
    ListingState.published: set(),  # Terminal state
}


class ListingNotFoundError(HTTPException):
    """Raised when a listing is not found or does not belong to the requesting seller."""

    def __init__(self, detail: str = "Listing not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class InvalidStateTransitionError(HTTPException):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, current_state: ListingState, target_state: ListingState):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state transition from '{current_state.value}' to '{target_state.value}'.",
        )


def parse_listing_uuid(listing_id: str) -> uuid.UUID:
    """Parse string listing_id into UUID, raising 404 if invalid."""
    try:
        return uuid.UUID(listing_id)
    except (ValueError, TypeError, AttributeError):
        raise ListingNotFoundError()


def get_listing_for_seller(db: Session, listing_id: str, seller_id: uuid.UUID) -> Listing:
    """Fetch a listing by ID, strictly verifying that it belongs to the authenticated seller.

    Raises:
        ListingNotFoundError (404): If the listing does not exist or belongs to another seller.
    """
    listing_uuid = parse_listing_uuid(listing_id)
    listing = db.query(Listing).filter(Listing.id == listing_uuid).first()
    if listing is None or listing.seller_id != seller_id:
        raise ListingNotFoundError()
    return listing


def create_or_get_listing(
    db: Session,
    seller_id: uuid.UUID,
    client_item_id: str,
    description: Optional[str] = None,
    photo_count: Optional[int] = None,
) -> Listing:
    """Create a new listing in 'queued' state for the authenticated seller.

    If a listing with (seller_id, client_item_id) already exists, returns the existing listing
    deterministically (idempotent creation). A retried upload may carry a typed
    description the first attempt did not, so it is filled in when missing.
    """
    typed = (description or "").strip() or None
    expected_photos = photo_count if photo_count and photo_count > 0 else None

    existing = db.query(Listing).filter(
        Listing.seller_id == seller_id,
        Listing.client_item_id == client_item_id,
    ).first()
    if existing is not None:
        changed = False
        if typed and not existing.typed_description:
            existing.typed_description = typed
            changed = True
        # A retry re-sends the whole set, so the latest count is the one the
        # pipeline should wait for.
        if expected_photos and existing.expected_photo_count != expected_photos:
            existing.expected_photo_count = expected_photos
            changed = True
        if changed:
            db.commit()
            db.refresh(existing)
        return existing

    listing = Listing(
        seller_id=seller_id,
        client_item_id=client_item_id,
        state=ListingState.queued,
        typed_description=typed,
        expected_photo_count=expected_photos,
    )
    try:
        db.add(listing)
        db.commit()
        db.refresh(listing)
        return listing
    except IntegrityError:
        db.rollback()
        existing = db.query(Listing).filter(
            Listing.seller_id == seller_id,
            Listing.client_item_id == client_item_id,
        ).first()
        if existing is not None:
            return existing
        raise


def list_seller_listings(db: Session, seller_id: uuid.UUID) -> List[Listing]:
    """Retrieve all listings belonging to the authenticated seller, ordered newest first."""
    return (
        db.query(Listing)
        .filter(Listing.seller_id == seller_id)
        .order_by(Listing.created_at.desc())
        .all()
    )


def validate_state_transition(current_state: ListingState, target_state: ListingState) -> None:
    """Validate that transition from current_state to target_state is permitted.

    Self-transitions (target_state == current_state) are idempotent and permitted.
    """
    if current_state == target_state:
        return
    allowed_next = VALID_STATE_TRANSITIONS.get(current_state, set())
    if target_state not in allowed_next:
        raise InvalidStateTransitionError(current_state=current_state, target_state=target_state)


def transition_listing(db: Session, listing: Listing, new_state: ListingState) -> Listing:
    """Validate and execute a state transition on a listing, updating the updated_at timestamp."""
    validate_state_transition(listing.state, new_state)
    if listing.state != new_state:
        listing.state = new_state
        listing.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(listing)
    return listing


def delete_listing_for_seller(db: Session, listing_id: str, seller_id: uuid.UUID) -> None:
    """Delete a listing the seller asked to be gone, with its media, rows and files.

    Ownership is verified first, so one seller can never delete another's listing.
    The child rows (media, suggestions, consent, result, approval) go with it
    through the configured cascades; the stored files are removed separately
    because nothing in the database points at them once the rows are gone.
    """
    listing = get_listing_for_seller(db=db, listing_id=listing_id, seller_id=seller_id)

    stored_paths = [media.storage_path for media in listing.media if media.storage_path]

    db.delete(listing)
    db.commit()

    # Best effort: the listing is already gone as far as the seller is concerned,
    # so a file that cannot be removed must not fail the request.
    for stored in stored_paths:
        delete_stored_file(Path(stored))

    storage_dir = Path(settings.MEDIA_STORAGE_DIR).resolve() / str(listing_id)
    try:
        if storage_dir.is_dir() and not any(storage_dir.iterdir()):
            storage_dir.rmdir()
    except Exception:
        pass
