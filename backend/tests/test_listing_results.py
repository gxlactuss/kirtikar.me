"""What the app reads back about a listing.

The pipeline used to compute a fact sheet and then discard it, and the read
endpoints answered from hardcoded sample data, so a silver necklace and a clay
pot both read back as the same Madhubani painting. These tests pin the run's
conclusions to the listing and to the payload the app parses.
"""
import uuid
from typing import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.listing import Listing
from app.models.listing_result import ListingResult
from app.models.seller import Seller
from app.models.suggestion import Suggestion
from app.schemas.enums import ListingState
from app.services.listing_view import to_listing_response
from app.services.pipeline.context import (
    FactSheetOutput,
    ImageStageOutput,
    PipelineContext,
    PriceStageOutput,
    SpeechStageOutput,
)
from app.services.pipeline.persist import save_attention_reason, save_pipeline_result


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def listing(db: Session) -> Listing:
    seller = Seller(
        id=uuid.uuid4(),
        firebase_uid="fb-results",
        phone_number="+919812345678",
        name="Radha",
        language="hi",
    )
    item = Listing(
        id=uuid.uuid4(),
        seller_id=seller.id,
        client_item_id="capture-1",
        state=ListingState.processing,
    )
    db.add_all([seller, item])
    db.commit()
    db.refresh(item)
    return item


def _context(listing: Listing, **overrides) -> PipelineContext:
    context = PipelineContext(listing_id=listing.id, seller_id=listing.seller_id)
    context.image_output = ImageStageOutput(
        image_count=1, image_paths=["a/clean.jpg"], detected_labels=[]
    )
    context.speech_output = SpeechStageOutput(
        audio_path="voice.m4a",
        transcript="Yeh chandi ka haar hai. Aath sau rupaye.",
        language="hi",
    )
    context.fact_sheet_output = FactSheetOutput(
        title="Handmade Silver Necklace",
        craft_type="Silver Filigree",
        material="Silver",
        story_summary="A necklace shaped by hand.",
        attributes={
            "dimensions": "40 cm",
            "primary_colors": ["Silver", "White"],
            "stated_price": 800.0,
            "missing_fields": [],
        },
    )
    context.price_output = PriceStageOutput(
        currency="INR",
        min_price=720.0,
        max_price=920.0,
        recommended_price=800.0,
    )
    for key, value in overrides.items():
        setattr(context, key, value)
    return context


# --------------------------------------------------------------------------
# The run's conclusions survive it
# --------------------------------------------------------------------------


def test_the_fact_sheet_is_written_to_the_listing(db: Session, listing: Listing):
    save_pipeline_result(db, listing, _context(listing))

    stored = db.query(ListingResult).filter_by(listing_id=listing.id).one()
    assert stored.title == "Handmade Silver Necklace"
    assert stored.material == "Silver"
    assert stored.size == "40 cm"
    assert stored.technique == "Silver Filigree"
    # Not a Madhubani painting, which is what every listing used to read back.
    assert "Madhubani" not in (stored.title or "")


def test_a_colour_list_becomes_readable_text(db: Session, listing: Listing):
    save_pipeline_result(db, listing, _context(listing))
    stored = db.query(ListingResult).filter_by(listing_id=listing.id).one()
    assert stored.colour == "Silver, White"


def test_money_is_stored_in_paise(db: Session, listing: Listing):
    """Rupees from the stages must never reach the app as a float."""
    save_pipeline_result(db, listing, _context(listing))
    stored = db.query(ListingResult).filter_by(listing_id=listing.id).one()

    assert stored.price_in_paise == 80000
    assert stored.suggested_price_in_paise == 80000
    assert stored.price_floor_in_paise == 72000
    assert isinstance(stored.price_in_paise, int)


def test_a_stated_price_beats_the_advisory_band(db: Session, listing: Listing):
    """What the artisan actually said is the price."""
    context = _context(listing)
    context.price_output = PriceStageOutput(
        currency="INR", min_price=1200.0, max_price=1800.0, recommended_price=1500.0
    )
    save_pipeline_result(db, listing, context)

    stored = db.query(ListingResult).filter_by(listing_id=listing.id).one()
    assert stored.price_in_paise == 80000, "the spoken 800 rupees must win"
    assert stored.suggested_price_in_paise == 150000


def test_an_unpriced_note_falls_back_to_the_recommendation(db: Session, listing: Listing):
    context = _context(listing)
    context.fact_sheet_output.attributes["stated_price"] = None
    save_pipeline_result(db, listing, context)

    stored = db.query(ListingResult).filter_by(listing_id=listing.id).one()
    assert stored.price_in_paise == 80000


def test_stock_defaults_to_one_rather_than_nothing(db: Session, listing: Listing):
    """A null quantity reads as zero stock in the app, which means sold out."""
    save_pipeline_result(db, listing, _context(listing))
    stored = db.query(ListingResult).filter_by(listing_id=listing.id).one()
    assert stored.quantity == 1


def test_running_again_updates_rather_than_duplicates(db: Session, listing: Listing):
    save_pipeline_result(db, listing, _context(listing))

    second = _context(listing)
    second.fact_sheet_output.title = "Handmade Silver Anklet"
    save_pipeline_result(db, listing, second)

    rows = db.query(ListingResult).filter_by(listing_id=listing.id).all()
    assert len(rows) == 1
    assert rows[0].title == "Handmade Silver Anklet"


def test_the_transcript_and_language_are_kept(db: Session, listing: Listing):
    save_pipeline_result(db, listing, _context(listing))
    stored = db.query(ListingResult).filter_by(listing_id=listing.id).one()
    assert stored.language == "hi"
    assert "chandi" in stored.transcript


# --------------------------------------------------------------------------
# Missing facts become questions, not inventions
# --------------------------------------------------------------------------


def test_missing_fields_become_suggestions(db: Session, listing: Listing):
    context = _context(listing)
    context.fact_sheet_output.attributes["missing_fields"] = ["price", "dimensions"]
    save_pipeline_result(db, listing, context)

    fields = {s.field for s in db.query(Suggestion).filter_by(listing_id=listing.id)}
    assert fields == {"price", "dimensions"}


def test_suggestions_are_replaced_not_appended_on_a_rerun(db: Session, listing: Listing):
    context = _context(listing)
    context.fact_sheet_output.attributes["missing_fields"] = ["price"]
    save_pipeline_result(db, listing, context)
    save_pipeline_result(db, listing, context)

    assert db.query(Suggestion).filter_by(listing_id=listing.id).count() == 1


def test_a_complete_note_raises_no_questions(db: Session, listing: Listing):
    save_pipeline_result(db, listing, _context(listing))
    assert db.query(Suggestion).filter_by(listing_id=listing.id).count() == 0


# --------------------------------------------------------------------------
# A halted run still explains itself
# --------------------------------------------------------------------------


def test_a_halted_run_records_why(db: Session, listing: Listing):
    context = PipelineContext(listing_id=listing.id, seller_id=listing.seller_id)
    save_attention_reason(db, listing, context, "This photo is too dark.")

    stored = db.query(ListingResult).filter_by(listing_id=listing.id).one()
    assert stored.follow_up_question == "This photo is too dark."


def test_a_finished_run_clears_an_earlier_question(db: Session, listing: Listing):
    save_attention_reason(db, listing, PipelineContext(listing_id=listing.id), "Too dark.")
    db.refresh(listing)
    save_pipeline_result(db, listing, _context(listing))

    stored = db.query(ListingResult).filter_by(listing_id=listing.id).one()
    assert stored.follow_up_question is None


def test_a_halted_run_keeps_what_it_did_work_out(db: Session, listing: Listing):
    context = _context(listing)
    save_attention_reason(db, listing, context, "Could not separate the item.")

    stored = db.query(ListingResult).filter_by(listing_id=listing.id).one()
    assert stored.title == "Handmade Silver Necklace"
    assert stored.follow_up_question == "Could not separate the item."


# --------------------------------------------------------------------------
# The payload the app parses
# --------------------------------------------------------------------------


def test_the_response_carries_the_fact_sheet(db: Session, listing: Listing):
    save_pipeline_result(db, listing, _context(listing))
    db.refresh(listing)

    body = to_listing_response(listing).model_dump()
    assert body["title"] == "Handmade Silver Necklace"
    assert body["fact_sheet"]["material"] == "Silver"
    assert body["fact_sheet"]["size"] == "40 cm"
    assert body["fact_sheet"]["price_in_paise"] == 80000
    assert body["fact_sheet"]["quantity"] == 1
    assert body["suggested_price_in_paise"] == 80000


def test_an_unprocessed_listing_reports_no_facts_rather_than_fake_ones(
    db: Session, listing: Listing
):
    body = to_listing_response(listing).model_dump()
    assert body["title"] is None
    assert body["fact_sheet"]["material"] is None
    assert body["suggestions"] == []
    assert body["state"] == ListingState.processing


def test_the_response_keys_are_the_ones_the_app_reads(db: Session, listing: Listing):
    """The app maps snake_case to camelCase and reads these exact names."""
    save_pipeline_result(db, listing, _context(listing))
    db.refresh(listing)
    body = to_listing_response(listing).model_dump()

    for key in (
        "id",
        "client_item_id",
        "state",
        "title",
        "description",
        "image_urls",
        "fact_sheet",
        "suggestions",
        "follow_up_question",
        "suggested_price_in_paise",
        "price_floor_in_paise",
        "preview_url",
        "photo_consent",
        "story_consent",
        "views",
    ):
        assert key in body, f"the app expects '{key}'"

    for key in (
        "material",
        "size",
        "colour",
        "technique",
        "quantity",
        "price_in_paise",
        "hours_to_make",
        "material_cost_in_paise",
        "is_one_of_a_kind",
    ):
        assert key in body["fact_sheet"], f"the app expects fact_sheet.{key}"


def test_a_question_reaches_the_response(db: Session, listing: Listing):
    save_attention_reason(db, listing, PipelineContext(listing_id=listing.id), "Too dark.")
    db.refresh(listing)
    assert to_listing_response(listing).follow_up_question == "Too dark."


def test_synthetic_facts_are_flagged_as_not_live(db: Session, listing: Listing):
    """A demo that silently degraded must be tellable from one that worked."""
    save_pipeline_result(db, listing, _context(listing))
    db.refresh(listing)
    assert to_listing_response(listing).used_live_model is False


# --------------------------------------------------------------------------
# Facts nobody stated stay empty
# --------------------------------------------------------------------------


def test_an_unstated_size_is_not_filled_with_an_image_resolution(db: Session, listing: Listing):
    """"1024x768" was being shown to the artisan as the item's physical size.

    The fact sheet stage defaulted unstated dimensions, origin and colours to a
    sample painting's values, so a response could claim a size and list
    dimensions as missing at the same time.
    """
    from app.services.pipeline.stages.fact_sheet import FactSheetStage
    from app.services.llm.gemini import GeminiExtractionResult

    class _NoDetails:
        def extract_fact_sheet(self, **kwargs):
            return GeminiExtractionResult(
                title="Handmade Clay Pot",
                craft_type="Terracotta Pottery",
                material="Clay",
                story_summary="A pot.",
                stated_price=None,
                dimensions=None,
                origin=None,
                colors=[],
                missing_fields=["price"],
                attributes={"stated_price": None, "missing_fields": ["price"]},
                used_live_api=True,
            )

        # No _synthetic_fallback: the stage must call the real extraction.

    import app.services.pipeline.stages.fact_sheet as module

    original = module._get_gemini_extractor
    module._get_gemini_extractor = lambda: _NoDetails()
    try:
        context = _context(listing)
        context.fact_sheet_output = None
        result = FactSheetStage().run(context)
    finally:
        module._get_gemini_extractor = original

    attributes = context.fact_sheet_output.attributes
    assert attributes.get("dimensions") in (None, "", [])
    assert attributes.get("origin") in (None, "", [])
    assert not attributes.get("primary_colors")
    assert "1024x768" not in str(attributes)
    assert "Mithila" not in str(attributes)

    # And what is missing is asked about instead.
    assert "dimensions" in attributes["missing_fields"]
    assert "colors" in attributes["missing_fields"]

    save_pipeline_result(db, listing, context)
    stored = db.query(ListingResult).filter_by(listing_id=listing.id).one()
    assert stored.size is None
    assert stored.colour is None


# --------------------------------------------------------------------------
# A typed description instead of a recording
# --------------------------------------------------------------------------


def test_a_typed_description_stands_in_for_the_transcript(db: Session, listing: Listing):
    """The description step offers a keyboard as well as a microphone.

    With no audio the speech stage used to stop the run for missing audio, so a
    typed note left the listing queued for ever.
    """
    from app.services.pipeline.stages.speech import SpeechStage
    from app.services.pipeline.result import StageStatus

    listing.typed_description = "A clay water pot, nine inches tall, 450 rupees."
    db.commit()

    context = PipelineContext(
        listing_id=listing.id,
        typed_description=listing.typed_description,
        seller_language="hi",
    )
    result = SpeechStage().run(context)

    assert result.status == StageStatus.success
    assert context.speech_output.transcript == listing.typed_description
    assert context.speech_output.language == "hi"
    assert result.metadata["source"] == "typed"


def test_no_audio_and_no_typed_note_still_needs_attention(db: Session, listing: Listing):
    from app.services.pipeline.stages.speech import SpeechStage
    from app.services.pipeline.result import StageStatus

    result = SpeechStage().run(PipelineContext(listing_id=listing.id))
    assert result.status == StageStatus.needs_attention


def test_a_blank_typed_note_is_not_treated_as_a_description(db: Session, listing: Listing):
    from app.services.pipeline.stages.speech import SpeechStage
    from app.services.pipeline.result import StageStatus

    context = PipelineContext(listing_id=listing.id, typed_description="   \n  ")
    assert SpeechStage().run(context).status == StageStatus.needs_attention


def test_the_typed_description_is_stored_on_the_listing(db: Session):
    from app.services.listing import create_or_get_listing

    seller = Seller(
        id=uuid.uuid4(),
        firebase_uid="fb-typed",
        phone_number="+919800000001",
        name="Asha",
        language="mr",
    )
    db.add(seller)
    db.commit()

    created = create_or_get_listing(
        db, seller.id, "capture-typed", description="  A woven bamboo basket.  "
    )
    assert created.typed_description == "A woven bamboo basket."


def test_a_retried_upload_can_supply_a_description_the_first_one_lacked(db: Session):
    from app.services.listing import create_or_get_listing

    seller = Seller(
        id=uuid.uuid4(),
        firebase_uid="fb-retry",
        phone_number="+919800000002",
        name="Asha",
        language="mr",
    )
    db.add(seller)
    db.commit()

    first = create_or_get_listing(db, seller.id, "capture-retry")
    assert first.typed_description is None

    again = create_or_get_listing(
        db, seller.id, "capture-retry", description="A woven bamboo basket."
    )
    assert again.id == first.id, "creation must stay idempotent"
    assert again.typed_description == "A woven bamboo basket."
