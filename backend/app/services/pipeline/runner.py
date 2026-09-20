"""Pipeline runner orchestrating sequential stage execution, retries, and state transitions."""
import logging
import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.listing import Listing
from app.models.media import Media
from app.schemas.enums import ListingState
from app.services.listing import (
    InvalidStateTransitionError,
    ListingNotFoundError,
    get_listing_for_seller,
    transition_listing,
)
from app.services.pipeline.context import PipelineContext
from app.services.pipeline.persist import save_pipeline_result, save_attention_reason
from app.services.pipeline.result import PipelineResult, StageResult, StageStatus
from app.services.pipeline.stage import PipelineStage
from app.services.pipeline.stages.confidence import ConfidenceStage
from app.services.pipeline.stages.fact_sheet import FactSheetStage
from app.services.pipeline.stages.image import ImageStage
from app.services.pipeline.stages.price import PriceStage
from app.services.pipeline.stages.speech import SpeechStage

logger = logging.getLogger("app.services.pipeline")


def get_default_stages() -> List[PipelineStage]:
    """Provide the default ordered sequence of deterministic pipeline stages."""
    return [
        ImageStage(),
        SpeechStage(),
        FactSheetStage(),
        PriceStage(),
        ConfidenceStage(),
    ]


class PipelineRunner:
    """Orchestrator for executing the 5-stage listing cataloging pipeline with controlled retries."""

    def __init__(
        self,
        stages: Optional[List[PipelineStage]] = None,
        max_stage_attempts: Optional[int] = None,
    ) -> None:
        self.stages = stages if stages is not None else get_default_stages()
        self.max_stage_attempts = (
            max_stage_attempts
            if max_stage_attempts is not None
            else settings.PIPELINE_MAX_STAGE_ATTEMPTS
        )

    def run(
        self,
        listing_id: uuid.UUID,
        db: Session,
        seller_id: Optional[uuid.UUID] = None,
    ) -> PipelineResult:
        """Execute the pipeline on a persisted listing, updating the listing lifecycle state.

        Args:
            listing_id: Target listing UUID to process.
            db: Active database session.
            seller_id: Optional authenticated seller UUID for ownership verification.

        Returns:
            PipelineResult indicating final state, stage results, and success/attention reasons.
        """
        # 1. Load listing and verify ownership if seller_id provided
        if seller_id is not None:
            listing = get_listing_for_seller(db, str(listing_id), seller_id)
        else:
            listing = db.query(Listing).filter(Listing.id == listing_id).first()
            if listing is None:
                raise ListingNotFoundError()

        # 2. State guards: Only queued or needs_attention listings can enter processing
        if listing.state in (ListingState.published, ListingState.ready, ListingState.processing):
            raise InvalidStateTransitionError(listing.state, ListingState.processing)

        logger.info("Listing %s -> Initiating pipeline run from initial state '%s'", listing.id, listing.state.value)
        transition_listing(db, listing, ListingState.processing)

        # 3. Load associated media items
        media = db.query(Media).filter(Media.listing_id == listing.id).all()

        # 4. Build execution context
        context = PipelineContext(
            listing_id=listing.id,
            seller_id=listing.seller_id,
            seller_story=listing.seller.craft_story if listing.seller else None,
            typed_description=listing.typed_description,
            seller_language=listing.seller.language if listing.seller else None,
            media=media,
        )

        # 5. Execute stages in fixed sequence
        for stage in self.stages:
            stage_name = getattr(stage, "name", stage.__class__.__name__)
            stage_success = False

            for attempt in range(1, self.max_stage_attempts + 1):
                context.stage_attempts[stage_name] = attempt
                logger.info(
                    "Listing %s -> Stage '%s' starting attempt %d/%d",
                    listing.id,
                    stage_name,
                    attempt,
                    self.max_stage_attempts,
                )

                try:
                    res = stage.run(context)
                except Exception as exc:
                    logger.warning(
                        "Listing %s -> Stage '%s' attempt %d threw unhandled exception: %s",
                        listing.id,
                        stage_name,
                        attempt,
                        exc,
                    )
                    res = StageResult.fail(reason=f"Unhandled stage exception: {exc}")

                context.stage_results[stage_name] = res

                if res.status == StageStatus.success:
                    logger.info(
                        "Listing %s -> Stage '%s' succeeded on attempt %d",
                        listing.id,
                        stage_name,
                        attempt,
                    )
                    stage_success = True
                    break

                elif res.status == StageStatus.needs_attention:
                    logger.info(
                        "Listing %s -> Stage '%s' requires attention: %s",
                        listing.id,
                        stage_name,
                        res.reason,
                    )
                    # Needs attention halts the pipeline immediately without retry
                    save_attention_reason(db, listing, context, res.reason)
                    transition_listing(db, listing, ListingState.needs_attention)
                    return PipelineResult(
                        listing_id=listing.id,
                        final_state=ListingState.needs_attention,
                        stage_results=context.stage_results,
                        success=False,
                        reason=res.reason,
                    )

                elif res.status == StageStatus.failure:
                    if attempt < self.max_stage_attempts:
                        logger.warning(
                            "Listing %s -> Stage '%s' attempt %d failed (%s). Retrying...",
                            listing.id,
                            stage_name,
                            attempt,
                            res.reason,
                        )
                    else:
                        logger.error(
                            "Listing %s -> Stage '%s' exhausted all %d attempts (%s). Halting pipeline.",
                            listing.id,
                            stage_name,
                            self.max_stage_attempts,
                            res.reason,
                        )
                        save_attention_reason(db, listing, context, res.reason)
                        transition_listing(db, listing, ListingState.needs_attention)
                        return PipelineResult(
                            listing_id=listing.id,
                            final_state=ListingState.needs_attention,
                            stage_results=context.stage_results,
                            success=False,
                            reason=f"Stage '{stage_name}' failed after {self.max_stage_attempts} attempts: {res.reason}",
                        )

            if not stage_success:
                save_attention_reason(db, listing, context, f"Stage '{stage_name}' did not complete.")
                transition_listing(db, listing, ListingState.needs_attention)
                return PipelineResult(
                    listing_id=listing.id,
                    final_state=ListingState.needs_attention,
                    stage_results=context.stage_results,
                    success=False,
                    reason=f"Stage '{stage_name}' did not complete successfully.",
                )

        # 6. All stages succeeded -> store what was understood, then mark ready.
        # The result is written first so a listing is never 'ready' with nothing
        # to read back.
        result_row = save_pipeline_result(db, listing, context)

        # A photo the vision gate could not use does not invalidate the voice
        # note, so the run completed and its conclusions are saved above. The
        # listing still must not go out on an ungraded frame, so it waits in
        # needs_attention with the retake as its question.
        if context.photo_warnings:
            reason = " ".join(context.photo_warnings)
            result_row.follow_up_question = reason
            db.add(result_row)
            db.commit()
            transition_listing(db, listing, ListingState.needs_attention)
            logger.info(
                "Listing %s -> pipeline complete but photos need attention: %s",
                listing.id,
                reason,
            )
            return PipelineResult(
                listing_id=listing.id,
                final_state=ListingState.needs_attention,
                stage_results=context.stage_results,
                success=False,
                reason=reason,
            )

        transition_listing(db, listing, ListingState.ready)
        logger.info("Listing %s -> All pipeline stages succeeded. Transitioned to 'ready'.", listing.id)
        return PipelineResult(
            listing_id=listing.id,
            final_state=ListingState.ready,
            stage_results=context.stage_results,
            success=True,
        )


def run_listing_pipeline(
    listing_id: uuid.UUID,
    db: Session,
    seller_id: Optional[uuid.UUID] = None,
    runner: Optional[PipelineRunner] = None,
) -> PipelineResult:
    """Convenience functional entry point for executing the listing pipeline."""
    pipeline_runner = runner if runner is not None else PipelineRunner()
    return pipeline_runner.run(listing_id=listing_id, db=db, seller_id=seller_id)
