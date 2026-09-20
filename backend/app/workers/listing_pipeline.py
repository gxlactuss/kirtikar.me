"""Background worker that runs the cataloging pipeline after media upload."""
import logging
import uuid
from typing import Optional

from app.db.session import SessionLocal
from app.services.listing import InvalidStateTransitionError, ListingNotFoundError
from app.services.pipeline.runner import run_listing_pipeline

logger = logging.getLogger("app.workers.listing_pipeline")


def process_listing(listing_id: uuid.UUID, seller_id: Optional[uuid.UUID] = None) -> None:
    """Run the pipeline for a listing on its own database session.

    FastAPI closes the request-scoped session as soon as the upload response is
    sent, and this runs afterwards, so it opens and owns a session of its own.
    Nothing here may raise: a background task failure would otherwise be
    invisible to the caller, who has already received their 200.
    """
    db = SessionLocal()
    try:
        result = run_listing_pipeline(listing_id=listing_id, db=db, seller_id=seller_id)
        logger.info(
            "Listing %s -> pipeline finished in state '%s' (success=%s)%s",
            listing_id,
            result.final_state.value,
            result.success,
            f": {result.reason}" if result.reason else "",
        )
    except InvalidStateTransitionError:
        # Another upload already started the pipeline for this listing, or it is
        # finished. Both are ordinary races rather than errors.
        logger.info("Listing %s -> pipeline already running or complete; skipping", listing_id)
    except ListingNotFoundError:
        logger.warning("Listing %s -> vanished before the pipeline could run", listing_id)
    except Exception:
        logger.exception("Listing %s -> pipeline raised an unhandled error", listing_id)
    finally:
        db.close()
