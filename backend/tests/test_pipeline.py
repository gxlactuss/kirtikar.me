"""Comprehensive test suite for the deterministic listing pipeline runner."""
import uuid
from typing import Generator, List
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.listing import Listing
from app.models.media import Media
from app.models.seller import Seller
from app.schemas.enums import ListingState, MediaType
from app.services.listing import (
    InvalidStateTransitionError,
    ListingNotFoundError,
    transition_listing,
)
from app.services.pipeline.runner import get_default_stages
from app.services.pipeline import (
    ConfidenceStage,
    FactSheetStage,
    ImageStage,
    ImageStageOutput,
    PipelineContext,
    PipelineResult,
    PipelineRunner,
    PipelineStage,
    PriceStage,
    SpeechStage,
    StageResult,
    StageStatus,
    run_listing_pipeline,
)


@pytest.fixture(scope="function")
def test_engine():
    """Create an isolated in-memory SQLite database engine with foreign keys enabled."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def test_db(test_engine) -> Generator[Session, None, None]:
    """Provide an isolated database session bound to the in-memory engine."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="function")
def seeded_seller_and_listing(test_db: Session):
    """Create a Seller, a queued Listing, and valid image + audio Media records."""
    seller = Seller(
        id=uuid.uuid4(),
        firebase_uid="firebase-pipeline-seller",
        phone_number="+919876543210",
        name="Artisan Radha Devi",
        language="hi",
        cluster="Madhubani Cluster",
        ondc_seller_id="ONDC-IND-1001",
    )
    listing = Listing(
        id=uuid.uuid4(),
        seller_id=seller.id,
        client_item_id="pipeline-capture-001",
        state=ListingState.queued,
    )
    test_db.add_all([seller, listing])
    test_db.commit()

    image_media = Media(
        id=uuid.uuid4(),
        listing_id=listing.id,
        media_type=MediaType.image,
        original_filename="front_view.jpg",
        storage_path=f"{listing.id}/image1.jpg",
        mime_type="image/jpeg",
        file_size_bytes=245000,
    )
    audio_media = Media(
        id=uuid.uuid4(),
        listing_id=listing.id,
        media_type=MediaType.audio,
        original_filename="story.wav",
        storage_path=f"{listing.id}/audio1.wav",
        mime_type="audio/wav",
        file_size_bytes=1050000,
    )
    test_db.add_all([image_media, audio_media])
    test_db.commit()
    test_db.refresh(listing)

    return seller, listing


class TrackingStage:
    """Stage that records its execution in a shared tracker list."""

    def __init__(self, name: str, execution_log: List[str]) -> None:
        self.name = name
        self.execution_log = execution_log

    def run(self, context: PipelineContext) -> StageResult:
        self.execution_log.append(self.name)
        return StageResult.ok(output=f"{self.name}_data")


class TransientFailureStage:
    """Stage wrapper that fails N times before succeeding or running underlying stage."""

    def __init__(self, stage: PipelineStage, fail_times: int, fail_with_exception: bool = False) -> None:
        self.stage = stage
        self.name = getattr(stage, "name", "transient_stage")
        self.fail_times = fail_times
        self.fail_with_exception = fail_with_exception
        self.attempts = 0

    def run(self, context: PipelineContext) -> StageResult:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            if self.fail_with_exception:
                raise RuntimeError(f"Simulated transient exception on attempt {self.attempts}")
            return StageResult.fail(reason=f"Transient failure on attempt {self.attempts}")
        return self.stage.run(context)


def test_successful_pipeline_execution_and_state_ready(test_db: Session, seeded_seller_and_listing):
    """Verify queued listing transitions through processing to ready with all 5 stages populated."""
    seller, listing = seeded_seller_and_listing

    runner = PipelineRunner()
    result = runner.run(listing_id=listing.id, db=test_db, seller_id=seller.id)

    assert result.success is True
    assert result.final_state == ListingState.ready
    test_db.refresh(listing)
    assert listing.state == ListingState.ready

    # Check that all 5 stages succeeded
    assert "image" in result.stage_results
    assert "speech" in result.stage_results
    assert "fact_sheet" in result.stage_results
    assert "price" in result.stage_results
    assert "confidence" in result.stage_results

    for stage_name, stage_res in result.stage_results.items():
        assert stage_res.status == StageStatus.success
        assert stage_res.output is not None


class PhotoWarningImageStage:
    """Image stage standing in for one whose vision gate rejected a photo."""

    name = "image"

    def run(self, context: PipelineContext) -> StageResult:
        context.photo_warnings.append(
            "Photo 3: The item fills only 1.6% of the photo. Please move closer."
        )
        output = ImageStageOutput(
            image_count=1,
            image_paths=["raw/photo_3.jpg"],
            detected_labels=[],
            dimensions=[{"width": 720, "height": 480}],
        )
        context.image_output = output
        return StageResult.ok(output=output)


def test_unusable_photo_still_yields_the_spoken_facts(test_db: Session, seeded_seller_and_listing):
    """A photo the vision gate cannot use must not discard the voice note.

    Halting at the image stage left the artisan looking at a blank listing and a
    complaint about a photo, with nothing they had actually said.
    """
    seller, listing = seeded_seller_and_listing

    stages = [PhotoWarningImageStage()] + get_default_stages()[1:]
    runner = PipelineRunner(stages=stages)
    result = runner.run(listing_id=listing.id, db=test_db, seller_id=seller.id)

    # The photo is still a problem, so the listing waits rather than going out.
    assert result.final_state == ListingState.needs_attention
    assert "move closer" in result.reason

    # Every stage after the image ran, and what they understood was saved.
    for stage_name in ("speech", "fact_sheet", "price", "confidence"):
        assert result.stage_results[stage_name].status == StageStatus.success

    test_db.refresh(listing)
    stored = listing.result
    assert stored is not None
    assert stored.title
    assert stored.transcript
    assert stored.suggested_price_in_paise is not None
    assert "move closer" in stored.follow_up_question


def test_stages_execute_in_strict_authoritative_order(test_db: Session, seeded_seller_and_listing):
    """Verify pipeline stages run in exact order: image -> speech -> fact_sheet -> price -> confidence."""
    seller, listing = seeded_seller_and_listing

    execution_log: List[str] = []
    tracking_stages = [
        TrackingStage("image", execution_log),
        TrackingStage("speech", execution_log),
        TrackingStage("fact_sheet", execution_log),
        TrackingStage("price", execution_log),
        TrackingStage("confidence", execution_log),
    ]

    runner = PipelineRunner(stages=tracking_stages)
    result = runner.run(listing_id=listing.id, db=test_db, seller_id=seller.id)

    assert result.success is True
    assert execution_log == ["image", "speech", "fact_sheet", "price", "confidence"]


def test_stage_outputs_flow_through_context(test_db: Session, seeded_seller_and_listing):
    """Verify output from each stage is accessible and consumed by downstream stages."""
    seller, listing = seeded_seller_and_listing

    context_captures: List[PipelineContext] = []

    class InspectingConfidenceStage(ConfidenceStage):
        def run(self, context: PipelineContext) -> StageResult:
            context_captures.append(context)
            return super().run(context)

    stages = [
        ImageStage(),
        SpeechStage(),
        FactSheetStage(),
        PriceStage(),
        InspectingConfidenceStage(),
    ]

    runner = PipelineRunner(stages=stages)
    result = runner.run(listing_id=listing.id, db=test_db, seller_id=seller.id)
    assert result.success is True

    captured_ctx = context_captures[0]
    assert captured_ctx.image_output is not None
    assert captured_ctx.image_output.image_count == 1
    assert captured_ctx.speech_output is not None
    assert "handmade" in captured_ctx.speech_output.transcript.lower()
    assert captured_ctx.fact_sheet_output is not None
    # The offline extraction names no craft it was not told about.
    assert captured_ctx.fact_sheet_output.craft_type == "Handcraft"
    assert captured_ctx.price_output is not None
    assert captured_ctx.price_output.recommended_price == 1500.0
    assert captured_ctx.confidence_output is not None
    assert captured_ctx.confidence_output.overall_score >= 0.70


def test_missing_image_media_halts_pipeline_with_needs_attention(test_db: Session):
    """Verify listing without images transitions to needs_attention and downstream stages do not run."""
    seller = Seller(id=uuid.uuid4(), firebase_uid="seller-no-image")
    listing = Listing(id=uuid.uuid4(), seller_id=seller.id, client_item_id="no-img", state=ListingState.queued)
    test_db.add_all([seller, listing])
    test_db.commit()

    # Only attach audio, NO image
    audio = Media(id=uuid.uuid4(), listing_id=listing.id, media_type=MediaType.audio, storage_path="audio.wav")
    test_db.add(audio)
    test_db.commit()

    execution_log: List[str] = []
    stages = [
        ImageStage(),
        TrackingStage("speech", execution_log),
        TrackingStage("fact_sheet", execution_log),
    ]

    runner = PipelineRunner(stages=stages)
    result = runner.run(listing_id=listing.id, db=test_db, seller_id=seller.id)

    assert result.success is False
    assert result.final_state == ListingState.needs_attention
    assert "at least one image is required" in result.reason.lower()
    test_db.refresh(listing)
    assert listing.state == ListingState.needs_attention

    # Downstream stages should NOT have executed
    assert len(execution_log) == 0


def test_missing_speech_media_halts_pipeline_with_needs_attention(test_db: Session):
    """Verify listing without audio transitions to needs_attention at speech stage."""
    seller = Seller(id=uuid.uuid4(), firebase_uid="seller-no-audio")
    listing = Listing(id=uuid.uuid4(), seller_id=seller.id, client_item_id="no-aud", state=ListingState.queued)
    test_db.add_all([seller, listing])
    test_db.commit()

    # Only attach image, NO audio
    image = Media(id=uuid.uuid4(), listing_id=listing.id, media_type=MediaType.image, storage_path="img.jpg")
    test_db.add(image)
    test_db.commit()

    execution_log: List[str] = []
    stages = [
        ImageStage(),
        SpeechStage(),
        TrackingStage("fact_sheet", execution_log),
    ]

    runner = PipelineRunner(stages=stages)
    result = runner.run(listing_id=listing.id, db=test_db, seller_id=seller.id)

    assert result.success is False
    assert result.final_state == ListingState.needs_attention
    assert "voice note audio is required" in result.reason.lower()
    test_db.refresh(listing)
    assert listing.state == ListingState.needs_attention
    assert len(execution_log) == 0


def test_low_confidence_score_transitions_to_needs_attention(test_db: Session, seeded_seller_and_listing):
    """Verify ConfidenceStage returning score below threshold marks listing as needs_attention."""
    seller, listing = seeded_seller_and_listing

    stages = [
        ImageStage(),
        SpeechStage(),
        FactSheetStage(),
        PriceStage(),
        ConfidenceStage(threshold=0.80, forced_score=0.65),  # Force score below threshold
    ]

    runner = PipelineRunner(stages=stages)
    result = runner.run(listing_id=listing.id, db=test_db, seller_id=seller.id)

    assert result.success is False
    assert result.final_state == ListingState.needs_attention
    assert "below required threshold" in result.reason.lower()
    test_db.refresh(listing)
    assert listing.state == ListingState.needs_attention


def test_transient_failure_retries_and_succeeds(test_db: Session, seeded_seller_and_listing):
    """Verify transient stage failure retries up to max attempts and continues pipeline upon recovery."""
    seller, listing = seeded_seller_and_listing

    failing_speech = TransientFailureStage(SpeechStage(), fail_times=2)  # Fails attempts 1 & 2, succeeds on 3
    stages = [
        ImageStage(),
        failing_speech,
        FactSheetStage(),
        PriceStage(),
        ConfidenceStage(),
    ]

    runner = PipelineRunner(stages=stages, max_stage_attempts=3)
    result = runner.run(listing_id=listing.id, db=test_db, seller_id=seller.id)

    assert result.success is True
    assert result.final_state == ListingState.ready
    assert failing_speech.attempts == 3
    test_db.refresh(listing)
    assert listing.state == ListingState.ready


def test_unhandled_exception_retries_and_recovers(test_db: Session, seeded_seller_and_listing):
    """Verify unhandled stage exception is caught as a failure and retried."""
    seller, listing = seeded_seller_and_listing

    failing_price = TransientFailureStage(PriceStage(), fail_times=1, fail_with_exception=True)
    stages = [
        ImageStage(),
        SpeechStage(),
        FactSheetStage(),
        failing_price,
        ConfidenceStage(),
    ]

    runner = PipelineRunner(stages=stages, max_stage_attempts=3)
    result = runner.run(listing_id=listing.id, db=test_db, seller_id=seller.id)

    assert result.success is True
    assert failing_price.attempts == 2
    assert result.final_state == ListingState.ready


def test_exhausted_retries_halts_pipeline_to_needs_attention(test_db: Session, seeded_seller_and_listing):
    """Verify stage failing all retry attempts causes needs_attention and stops downstream execution."""
    seller, listing = seeded_seller_and_listing

    execution_log: List[str] = []
    permanently_failing_stage = TransientFailureStage(FactSheetStage(), fail_times=5)  # Max attempts is 3
    stages = [
        ImageStage(),
        SpeechStage(),
        permanently_failing_stage,
        TrackingStage("price", execution_log),
    ]

    runner = PipelineRunner(stages=stages, max_stage_attempts=3)
    result = runner.run(listing_id=listing.id, db=test_db, seller_id=seller.id)

    assert result.success is False
    assert result.final_state == ListingState.needs_attention
    assert permanently_failing_stage.attempts == 3
    assert "failed after 3 attempts" in result.reason.lower()
    test_db.refresh(listing)
    assert listing.state == ListingState.needs_attention
    # Downstream price stage did NOT execute
    assert len(execution_log) == 0


def test_earlier_stages_not_rerun_during_downstream_retry(test_db: Session, seeded_seller_and_listing):
    """Verify that earlier successful stages are not re-executed when a later stage retries."""
    seller, listing = seeded_seller_and_listing

    image_counter = {"runs": 0}

    class CountingImageStage(ImageStage):
        def run(self, context: PipelineContext) -> StageResult:
            image_counter["runs"] += 1
            return super().run(context)

    failing_speech = TransientFailureStage(SpeechStage(), fail_times=2)
    stages = [
        CountingImageStage(),
        failing_speech,
        FactSheetStage(),
        PriceStage(),
        ConfidenceStage(),
    ]

    runner = PipelineRunner(stages=stages, max_stage_attempts=3)
    result = runner.run(listing_id=listing.id, db=test_db, seller_id=seller.id)

    assert result.success is True
    # Image stage executed exactly ONCE, even though speech stage was attempted 3 times
    assert image_counter["runs"] == 1
    assert failing_speech.attempts == 3


def test_needs_attention_is_not_retried(test_db: Session, seeded_seller_and_listing):
    """Verify needs_attention result halts immediately on attempt 1 without retrying."""
    seller, listing = seeded_seller_and_listing

    attention_counter = {"runs": 0}

    class OnceAttentionStage:
        name = "custom_attention"

        def run(self, context: PipelineContext) -> StageResult:
            attention_counter["runs"] += 1
            return StageResult.attention("Artisan input needed on material")

    stages = [
        ImageStage(),
        SpeechStage(),
        OnceAttentionStage(),
    ]

    runner = PipelineRunner(stages=stages, max_stage_attempts=3)
    result = runner.run(listing_id=listing.id, db=test_db, seller_id=seller.id)

    assert result.success is False
    assert result.final_state == ListingState.needs_attention
    # Exactly 1 attempt, NOT 3
    assert attention_counter["runs"] == 1


def test_published_listing_cannot_be_processed(test_db: Session, seeded_seller_and_listing):
    """Verify attempting to run pipeline on a published listing raises invalid transition error."""
    seller, listing = seeded_seller_and_listing
    transition_listing(test_db, listing, ListingState.processing)
    transition_listing(test_db, listing, ListingState.ready)
    transition_listing(test_db, listing, ListingState.published)

    runner = PipelineRunner()
    with pytest.raises(InvalidStateTransitionError):
        runner.run(listing_id=listing.id, db=test_db, seller_id=seller.id)


def test_ready_listing_cannot_be_reprocessed(test_db: Session, seeded_seller_and_listing):
    """Verify ready listing does not casually rerun the pipeline."""
    seller, listing = seeded_seller_and_listing
    transition_listing(test_db, listing, ListingState.processing)
    transition_listing(test_db, listing, ListingState.ready)

    runner = PipelineRunner()
    with pytest.raises(InvalidStateTransitionError):
        runner.run(listing_id=listing.id, db=test_db, seller_id=seller.id)


def test_processing_listing_blocks_concurrent_pipeline_start(test_db: Session, seeded_seller_and_listing):
    """Verify listing currently in processing state cannot start a competing pipeline run."""
    seller, listing = seeded_seller_and_listing
    transition_listing(test_db, listing, ListingState.processing)

    runner = PipelineRunner()
    with pytest.raises(InvalidStateTransitionError):
        runner.run(listing_id=listing.id, db=test_db, seller_id=seller.id)


def test_pipeline_can_be_restarted_from_needs_attention(test_db: Session, seeded_seller_and_listing):
    """Verify a listing in needs_attention can re-enter processing when re-run."""
    seller, listing = seeded_seller_and_listing
    transition_listing(test_db, listing, ListingState.processing)
    transition_listing(test_db, listing, ListingState.needs_attention)

    runner = PipelineRunner()
    result = runner.run(listing_id=listing.id, db=test_db, seller_id=seller.id)

    assert result.success is True
    assert result.final_state == ListingState.ready
    test_db.refresh(listing)
    assert listing.state == ListingState.ready


def test_final_listing_state_persisted_across_fresh_session(test_engine, seeded_seller_and_listing):
    """Verify final state set by the runner survives closing and re-opening the database session."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    seller, listing = seeded_seller_and_listing
    listing_id = listing.id

    # Run pipeline in session 1
    sess1 = SessionLocal()
    runner = PipelineRunner()
    res = runner.run(listing_id=listing_id, db=sess1)
    assert res.success is True
    sess1.close()

    # Verify state in fresh session 2
    sess2 = SessionLocal()
    reloaded = sess2.query(Listing).filter(Listing.id == listing_id).first()
    assert reloaded is not None
    assert reloaded.state == ListingState.ready
    sess2.close()


def test_seller_ownership_enforced_when_seller_id_provided(test_db: Session, seeded_seller_and_listing):
    """Verify runner rejects execution with ListingNotFoundError if seller_id does not match listing owner."""
    seller_a, listing = seeded_seller_and_listing
    foreign_seller_id = uuid.uuid4()

    runner = PipelineRunner()
    with pytest.raises(ListingNotFoundError):
        runner.run(listing_id=listing.id, db=test_db, seller_id=foreign_seller_id)


def test_functional_run_listing_pipeline_entry_point(test_db: Session, seeded_seller_and_listing):
    """Verify convenience entry point run_listing_pipeline executes successfully."""
    seller, listing = seeded_seller_and_listing

    result = run_listing_pipeline(listing_id=listing.id, db=test_db, seller_id=seller.id)
    assert result.success is True
    assert result.final_state == ListingState.ready


def test_nonexistent_listing_raises_not_found(test_db: Session):
    """Verify runner raises ListingNotFoundError when listing_id does not exist."""
    runner = PipelineRunner()
    with pytest.raises(ListingNotFoundError):
        runner.run(listing_id=uuid.uuid4(), db=test_db)


def test_custom_max_stage_attempts_override(test_db: Session, seeded_seller_and_listing):
    """Verify max_stage_attempts parameter overrides default setting."""
    seller, listing = seeded_seller_and_listing
    failing_speech = TransientFailureStage(SpeechStage(), fail_times=1)
    runner = PipelineRunner(stages=[ImageStage(), failing_speech], max_stage_attempts=1)
    result = runner.run(listing_id=listing.id, db=test_db, seller_id=seller.id)
    assert result.success is False
    assert result.final_state == ListingState.needs_attention
    assert failing_speech.attempts == 1


def test_stage_result_factories_and_status():
    """Verify StageResult factory methods produce expected statuses and payload attributes."""
    ok_res = StageResult.ok(output={"foo": "bar"}, metadata={"latency_ms": 12})
    assert ok_res.status == StageStatus.success
    assert ok_res.output == {"foo": "bar"}
    assert ok_res.metadata["latency_ms"] == 12

    att_res = StageResult.attention("Need artisan input")
    assert att_res.status == StageStatus.needs_attention
    assert att_res.reason == "Need artisan input"

    fail_res = StageResult.fail("Connection timed out")
    assert fail_res.status == StageStatus.failure
    assert fail_res.reason == "Connection timed out"


def test_image_stage_filters_only_image_media(seeded_seller_and_listing):
    """Verify ImageStage filters out non-image media and builds ImageStageOutput."""
    seller, listing = seeded_seller_and_listing
    ctx = PipelineContext(listing_id=listing.id, seller_id=seller.id, media=listing.media)
    stage = ImageStage()
    res = stage.run(ctx)
    assert res.status == StageStatus.success
    assert ctx.image_output is not None
    assert ctx.image_output.image_count == 1
    assert len(ctx.image_output.detected_labels) > 0


def test_speech_stage_detects_audio_media(seeded_seller_and_listing):
    """Verify SpeechStage finds audio media and populates SpeechStageOutput."""
    seller, listing = seeded_seller_and_listing
    ctx = PipelineContext(listing_id=listing.id, seller_id=seller.id, media=listing.media)
    stage = SpeechStage()
    res = stage.run(ctx)
    assert res.status == StageStatus.success
    assert ctx.speech_output is not None
    assert ctx.speech_output.duration_seconds > 0
    assert len(ctx.speech_output.transcript) > 0


def test_fact_sheet_stage_requires_prerequisites():
    """Verify FactSheetStage halts with needs_attention if image/speech outputs are absent."""
    ctx = PipelineContext(listing_id=uuid.uuid4())
    stage = FactSheetStage()
    res = stage.run(ctx)
    assert res.status == StageStatus.needs_attention
    assert "missing prerequisite" in res.reason.lower()


def test_price_stage_requires_fact_sheet_prerequisite():
    """Verify PriceStage halts with needs_attention if fact sheet is absent."""
    ctx = PipelineContext(listing_id=uuid.uuid4())
    stage = PriceStage()
    res = stage.run(ctx)
    assert res.status == StageStatus.needs_attention
    assert "missing prerequisite" in res.reason.lower()


def test_confidence_stage_requires_all_prerequisites():
    """Verify ConfidenceStage halts with needs_attention if any previous stage output is absent."""
    ctx = PipelineContext(listing_id=uuid.uuid4())
    stage = ConfidenceStage()
    res = stage.run(ctx)
    assert res.status == StageStatus.needs_attention
    assert "missing prerequisite" in res.reason.lower()


def test_confidence_stage_score_above_threshold_succeeds(seeded_seller_and_listing):
    """Verify ConfidenceStage succeeds when overall score exceeds configured threshold."""
    seller, listing = seeded_seller_and_listing
    ctx = PipelineContext(listing_id=listing.id, seller_id=seller.id, media=listing.media)
    ImageStage().run(ctx)
    SpeechStage().run(ctx)
    FactSheetStage().run(ctx)
    PriceStage().run(ctx)
    res = ConfidenceStage(threshold=0.70, forced_score=0.95).run(ctx)
    assert res.status == StageStatus.success
    assert ctx.confidence_output is not None
    assert ctx.confidence_output.overall_score == 0.95
    assert ctx.confidence_output.is_confident is True

def test_image_stage_live_path_success(tmp_path, monkeypatch):
    """Verify ImageStage live processing branch with mock files under MEDIA_STORAGE_DIR."""
    storage_dir = tmp_path / "media"
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.core.config.settings.MEDIA_STORAGE_DIR", str(storage_dir))

    listing_id = uuid.uuid4()
    media_id = uuid.uuid4()
    media_rel_path = f"{listing_id}/test.jpg"
    full_img_path = storage_dir / media_rel_path
    full_img_path.parent.mkdir(parents=True, exist_ok=True)
    full_img_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    media = Media(id=media_id, listing_id=listing_id, media_type=MediaType.image, storage_path=media_rel_path)
    ctx = PipelineContext(listing_id=listing_id, media=[media])

    class MockStation:
        def process_image(self, input_path, output_dir, item_id):
            clean_file = Path(output_dir) / f"{item_id}_clean.jpg"
            clean_file.parent.mkdir(parents=True, exist_ok=True)
            clean_file.write_text("dummy")
            return {
                "quality": {"passed": True, "blur_score": 100.0, "warnings": []},
                "outputs": {"clean_image": str(clean_file)},
            }

    monkeypatch.setattr("app.services.pipeline.stages.image._get_station", lambda: MockStation())

    stage = ImageStage()
    res = stage.run(ctx)

    assert res.status == StageStatus.success
    assert ctx.image_output is not None
    assert ctx.image_output.image_count == 1
    assert ctx.image_output.image_paths[0] == f"{listing_id}/vision/{media_id}_clean.jpg"
    # The composite has to be recorded on the media row, or the endpoint that
    # serves this photo to the app goes on returning the raw camera frame and
    # the studio image never reaches the listing.
    assert media.processed_path == f"{listing_id}/vision/{media_id}_clean.jpg"


def test_image_stage_live_path_quality_failure(tmp_path, monkeypatch):
    """A photo that fails the quality gate is noted for retake, not fatal to the run."""
    storage_dir = tmp_path / "media"
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.core.config.settings.MEDIA_STORAGE_DIR", str(storage_dir))

    listing_id = uuid.uuid4()
    media_id = uuid.uuid4()
    media_rel_path = f"{listing_id}/blurry.jpg"
    full_img_path = storage_dir / media_rel_path
    full_img_path.parent.mkdir(parents=True, exist_ok=True)
    full_img_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    media = Media(id=media_id, listing_id=listing_id, media_type=MediaType.image, storage_path=media_rel_path)
    ctx = PipelineContext(listing_id=listing_id, media=[media])

    class MockStation:
        def process_image(self, input_path, output_dir, item_id):
            return {
                "quality": {"passed": False, "warnings": ["Photo is blurry (score 15.2 < 30.0)"]},
                "outputs": {},
            }

    monkeypatch.setattr("app.services.pipeline.stages.image._get_station", lambda: MockStation())

    stage = ImageStage()
    res = stage.run(ctx)

    # The run continues so the voice note is still transcribed and understood;
    # the blurry frame is carried through raw and the retake is asked for at the
    # end of the run instead.
    assert res.status == StageStatus.success
    assert ctx.photo_warnings
    assert "blurry" in ctx.photo_warnings[0].lower()
    assert ctx.image_output.image_paths == [media_rel_path]
    assert media.processed_path is None


def test_speech_stage_path_traversal_detection(tmp_path, monkeypatch):
    """Verify SpeechStage blocks path traversal attempts in media storage paths."""
    storage_dir = tmp_path / "media"
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.core.config.settings.MEDIA_STORAGE_DIR", str(storage_dir))

    listing_id = uuid.uuid4()
    media = Media(
        id=uuid.uuid4(),
        listing_id=listing_id,
        media_type=MediaType.audio,
        storage_path="../../etc/evil.wav",
    )
    ctx = PipelineContext(listing_id=listing_id, media=[media])

    stage = SpeechStage()
    res = stage.run(ctx)
    assert res.status == StageStatus.failure
    assert "invalid media storage path" in res.reason.lower()


def test_speech_stage_with_voice_station_mock(tmp_path, monkeypatch):
    """Verify SpeechStage invokes VoiceStation and populates context correctly."""
    storage_dir = tmp_path / "media"
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.core.config.settings.MEDIA_STORAGE_DIR", str(storage_dir))

    listing_id = uuid.uuid4()
    audio_path = f"{listing_id}/story.wav"
    full_path = storage_dir / audio_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(b"RIFF" + b"\x00" * 40)

    media = Media(
        id=uuid.uuid4(),
        listing_id=listing_id,
        media_type=MediaType.audio,
        storage_path=audio_path,
    )
    ctx = PipelineContext(listing_id=listing_id, media=[media])

    from app.services.voice.pipeline import VoiceTranscriptionResult

    class MockVoiceStation:
        def process_audio(self, audio_path, allow_synthetic_fallback=True):
            return VoiceTranscriptionResult(
                transcript="Handmade bamboo basket crafted in Assam.",
                language_code="as",
                duration_seconds=12.0,
            )

    monkeypatch.setattr("app.services.pipeline.stages.speech._get_voice_station", lambda: MockVoiceStation())

    stage = SpeechStage()
    res = stage.run(ctx)
    assert res.status == StageStatus.success
    assert ctx.speech_output is not None
    assert ctx.speech_output.transcript == "Handmade bamboo basket crafted in Assam."
    assert ctx.speech_output.language == "as"
    assert ctx.speech_output.duration_seconds == 12.0


def test_fact_sheet_stage_with_gemini_mock(monkeypatch):
    """Verify FactSheetStage calls GeminiExtractor and enriches attributes with missing fields."""
    from app.services.pipeline.context import ImageStageOutput, SpeechStageOutput
    from app.services.llm.gemini import GeminiExtractionResult

    ctx = PipelineContext(listing_id=uuid.uuid4())
    ctx.image_output = ImageStageOutput(
        image_count=2,
        image_paths=["path1.jpg", "path2.jpg"],
        detected_labels=["pottery"],
        dimensions=[{"width": 1024, "height": 1024}],
    )
    ctx.speech_output = SpeechStageOutput(
        audio_path="dummy.wav",
        transcript="Clay pot made using river soil, asking 450 rupees.",
        language="hi",
    )

    class MockGeminiExtractor:
        def extract_fact_sheet(self, transcript, detected_language="hi", image_path=None, seller_story=None, allow_synthetic_fallback=True):
            return GeminiExtractionResult(
                title="Handcrafted Terracotta Clay Pot",
                craft_type="Terracotta Pottery",
                material="River clay, natural red soil",
                story_summary="Crafted using riverbed soil on a traditional potter wheel.",
                stated_price=450.0,
                dimensions="15x15 cm",
                origin="Gorakhpur, Uttar Pradesh",
                colors=["terracotta", "red ochre"],
                missing_fields=[],
                attributes={
                    "stated_price": 450.0,
                    "dimensions": "15x15 cm",
                    "origin": "Gorakhpur, Uttar Pradesh",
                    "primary_colors": ["terracotta", "red ochre"],
                    "missing_fields": [],
                },
            )

    monkeypatch.setattr("app.services.pipeline.stages.fact_sheet._get_gemini_extractor", lambda: MockGeminiExtractor())

    stage = FactSheetStage()
    res = stage.run(ctx)

    assert res.status == StageStatus.success
    assert ctx.fact_sheet_output is not None
    assert ctx.fact_sheet_output.title == "Handcrafted Terracotta Clay Pot"
    assert ctx.fact_sheet_output.craft_type == "Terracotta Pottery"
    assert ctx.fact_sheet_output.attributes["stated_price"] == 450.0
    assert ctx.fact_sheet_output.attributes["image_count"] == 2


def test_price_stage_adopts_stated_price():
    """Verify PriceStage adopts artisan's stated price if available."""
    from app.services.pipeline.context import FactSheetOutput

    ctx = PipelineContext(listing_id=uuid.uuid4())
    ctx.fact_sheet_output = FactSheetOutput(
        title="Terracotta Handi",
        craft_type="Pottery",
        material="Clay",
        story_summary="Handmade pot",
        attributes={"stated_price": 600.0},
    )

    stage = PriceStage()
    res = stage.run(ctx)

    assert res.status == StageStatus.success
    assert ctx.price_output is not None
    assert ctx.price_output.recommended_price == 600.0
    assert ctx.price_output.min_price == 540.0
    assert ctx.price_output.max_price == 690.0
    assert res.metadata.get("stated_by_artisan") is True


def test_price_stage_generates_ai_bounds_when_price_not_stated():
    """Verify PriceStage estimates fair price bounds when price was not mentioned."""
    from app.services.pipeline.context import FactSheetOutput

    ctx = PipelineContext(listing_id=uuid.uuid4())
    ctx.fact_sheet_output = FactSheetOutput(
        title="Handmade Coaster",
        craft_type="Jute Craft",
        material="Jute fiber",
        story_summary="Handwoven coasters",
        attributes={"stated_price": None},
    )

    stage = PriceStage()
    res = stage.run(ctx)

    assert res.status == StageStatus.success
    assert ctx.price_output is not None
    assert ctx.price_output.recommended_price == 1500.0
    assert res.metadata.get("stated_by_artisan") is False