"""Tests for PostgreSQL persistence domain models, relationships, and metadata."""
import uuid
from datetime import datetime, timezone
import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, UniqueConstraint
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import get_db, SessionLocal
import app.models  # ensure models are imported
from app.models import (
    Seller,
    Listing,
    Media,
    ListingConsent,
    Suggestion,
    ListingApproval,
)
from app.schemas.enums import ListingState, MediaType


EXPECTED_TABLES = {
    "sellers",
    "listings",
    "media",
    "listing_consents",
    "suggestions",
    "listing_approvals",
    # Where a pipeline run's conclusions are kept, so the app can read back
    # what was actually understood about a listing.
    "listing_results",
}


def test_metadata_contains_exact_domain_tables():
    """Verify Base.metadata contains exactly the application tables."""
    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES


def test_seller_columns_and_nullability():
    """Verify sellers table column definitions and nullability."""
    table = Base.metadata.tables["sellers"]
    columns = {c.name: c for c in table.columns}

    assert "id" in columns
    assert columns["id"].primary_key is True

    assert "name" in columns
    assert columns["name"].nullable is False

    assert "language" in columns
    assert columns["language"].nullable is False

    assert "cluster" in columns
    assert columns["cluster"].nullable is True

    assert "ondc_seller_id" in columns
    assert columns["ondc_seller_id"].nullable is True

    assert "firebase_uid" in columns
    assert columns["firebase_uid"].nullable is True

    assert "phone_number" in columns
    assert columns["phone_number"].nullable is True

    assert "created_at" in columns
    assert columns["created_at"].nullable is False

    assert "updated_at" in columns
    assert columns["updated_at"].nullable is False


def test_listing_columns_and_nullability():
    """Verify listings table column definitions and nullability."""
    table = Base.metadata.tables["listings"]
    columns = {c.name: c for c in table.columns}

    assert "id" in columns
    assert columns["id"].primary_key is True

    assert "seller_id" in columns
    assert columns["seller_id"].nullable is False

    assert "client_item_id" in columns
    assert columns["client_item_id"].nullable is False

    assert "state" in columns
    assert columns["state"].nullable is False

    assert "created_at" in columns
    assert columns["created_at"].nullable is False

    assert "updated_at" in columns
    assert columns["updated_at"].nullable is False


def test_media_columns_and_nullability():
    """Verify media table column definitions and nullability."""
    table = Base.metadata.tables["media"]
    columns = {c.name: c for c in table.columns}

    assert "id" in columns
    assert columns["id"].primary_key is True

    assert "listing_id" in columns
    assert columns["listing_id"].nullable is False

    assert "media_type" in columns
    assert columns["media_type"].nullable is False

    assert "original_filename" in columns
    assert columns["original_filename"].nullable is True

    assert "storage_path" in columns
    assert columns["storage_path"].nullable is True

    assert "mime_type" in columns
    assert columns["mime_type"].nullable is True

    assert "file_size_bytes" in columns
    assert columns["file_size_bytes"].nullable is True

    assert "created_at" in columns
    assert columns["created_at"].nullable is False

    assert "updated_at" in columns
    assert columns["updated_at"].nullable is False


def test_listing_consents_columns_and_nullability():
    """Verify listing_consents table column definitions and nullability."""
    table = Base.metadata.tables["listing_consents"]
    columns = {c.name: c for c in table.columns}

    assert "id" in columns
    assert columns["id"].primary_key is True

    assert "listing_id" in columns
    assert columns["listing_id"].nullable is False

    assert "photo_consent" in columns
    assert columns["photo_consent"].nullable is False

    assert "story_consent" in columns
    assert columns["story_consent"].nullable is False

    assert "created_at" in columns
    assert columns["created_at"].nullable is False

    assert "updated_at" in columns
    assert columns["updated_at"].nullable is False

    # ready_to_publish must NOT exist as a persisted column
    assert "ready_to_publish" not in columns


def test_suggestions_columns_and_nullability():
    """Verify suggestions table column definitions and nullability."""
    table = Base.metadata.tables["suggestions"]
    columns = {c.name: c for c in table.columns}

    assert "id" in columns
    assert columns["id"].primary_key is True

    assert "listing_id" in columns
    assert columns["listing_id"].nullable is False

    assert "field" in columns
    assert columns["field"].nullable is False

    assert "value" in columns
    assert columns["value"].nullable is False

    assert "reason" in columns
    assert columns["reason"].nullable is True

    assert "approved" in columns
    assert columns["approved"].nullable is True

    assert "created_at" in columns
    assert columns["created_at"].nullable is False

    assert "updated_at" in columns
    assert columns["updated_at"].nullable is False


def test_listing_approvals_columns_and_nullability():
    """Verify listing_approvals table column definitions and nullability."""
    table = Base.metadata.tables["listing_approvals"]
    columns = {c.name: c for c in table.columns}

    assert "id" in columns
    assert columns["id"].primary_key is True

    assert "listing_id" in columns
    assert columns["listing_id"].nullable is False

    assert "approved" in columns
    assert columns["approved"].nullable is False

    assert "approved_at" in columns
    assert columns["approved_at"].nullable is True

    assert "created_at" in columns
    assert columns["created_at"].nullable is False

    assert "updated_at" in columns
    assert columns["updated_at"].nullable is False


def test_metadata_unique_constraints():
    """Verify all specified unique constraints exist in metadata."""
    # UNIQUE(sellers.ondc_seller_id)
    sellers_uqs = [
        c for c in Base.metadata.tables["sellers"].constraints
        if isinstance(c, UniqueConstraint)
    ]
    seller_uq_cols = [{col.name for col in c.columns} for c in sellers_uqs]
    assert {"ondc_seller_id"} in seller_uq_cols
    assert {"firebase_uid"} in seller_uq_cols
    assert {"phone_number"} in seller_uq_cols

    # UNIQUE(seller_id, client_item_id) on listings
    listings_uqs = [
        c for c in Base.metadata.tables["listings"].constraints
        if isinstance(c, UniqueConstraint)
    ]
    listings_uq_cols = [{col.name for col in c.columns} for c in listings_uqs]
    assert {"seller_id", "client_item_id"} in listings_uq_cols

    # UNIQUE(listing_consents.listing_id)
    consents_uqs = [
        c for c in Base.metadata.tables["listing_consents"].constraints
        if isinstance(c, UniqueConstraint)
    ]
    consents_uq_cols = [{col.name for col in c.columns} for c in consents_uqs]
    assert {"listing_id"} in consents_uq_cols

    # UNIQUE(listing_approvals.listing_id)
    approvals_uqs = [
        c for c in Base.metadata.tables["listing_approvals"].constraints
        if isinstance(c, UniqueConstraint)
    ]
    approvals_uq_cols = [{col.name for col in c.columns} for c in approvals_uqs]
    assert {"listing_id"} in approvals_uq_cols


def test_metadata_foreign_keys_and_cascades():
    """Verify foreign keys and cascading delete configurations."""
    # listings.seller_id -> sellers.id (ondelete CASCADE)
    listing_fks = list(Base.metadata.tables["listings"].foreign_keys)
    assert len(listing_fks) == 1
    fk = listing_fks[0]
    assert fk.target_fullname == "sellers.id"
    assert fk.ondelete == "CASCADE"

    # media.listing_id -> listings.id (ondelete CASCADE)
    media_fks = list(Base.metadata.tables["media"].foreign_keys)
    assert len(media_fks) == 1
    assert media_fks[0].target_fullname == "listings.id"
    assert media_fks[0].ondelete == "CASCADE"

    # listing_consents.listing_id -> listings.id (ondelete CASCADE)
    consent_fks = list(Base.metadata.tables["listing_consents"].foreign_keys)
    assert len(consent_fks) == 1
    assert consent_fks[0].target_fullname == "listings.id"
    assert consent_fks[0].ondelete == "CASCADE"

    # suggestions.listing_id -> listings.id (ondelete CASCADE)
    suggestion_fks = list(Base.metadata.tables["suggestions"].foreign_keys)
    assert len(suggestion_fks) == 1
    assert suggestion_fks[0].target_fullname == "listings.id"
    assert suggestion_fks[0].ondelete == "CASCADE"

    # listing_approvals.listing_id -> listings.id (ondelete CASCADE)
    approval_fks = list(Base.metadata.tables["listing_approvals"].foreign_keys)
    assert len(approval_fks) == 1
    assert approval_fks[0].target_fullname == "listings.id"
    assert approval_fks[0].ondelete == "CASCADE"


def test_required_indexes():
    """Verify required indexes are defined on metadata."""
    # listings.seller_id
    listings_idx_cols = [
        {col.name for col in idx.columns}
        for idx in Base.metadata.tables["listings"].indexes
    ]
    assert {"seller_id"} in listings_idx_cols
    assert {"state"} in listings_idx_cols

    # media.listing_id
    media_idx_cols = [
        {col.name for col in idx.columns}
        for idx in Base.metadata.tables["media"].indexes
    ]
    assert {"listing_id"} in media_idx_cols

    # suggestions.listing_id
    suggestions_idx_cols = [
        {col.name for col in idx.columns}
        for idx in Base.metadata.tables["suggestions"].indexes
    ]
    assert {"listing_id"} in suggestions_idx_cols

    # listing_consents.listing_id
    consent_idx_cols = [
        {col.name for col in idx.columns}
        for idx in Base.metadata.tables["listing_consents"].indexes
    ]
    assert {"listing_id"} in consent_idx_cols

    # listing_approvals.listing_id
    approval_idx_cols = [
        {col.name for col in idx.columns}
        for idx in Base.metadata.tables["listing_approvals"].indexes
    ]
    assert {"listing_id"} in approval_idx_cols


def test_relationships_configuration():
    """Verify SQLAlchemy ORM relationship mappers are correctly bound."""
    seller_mapper = inspect(Seller)
    assert "listings" in seller_mapper.relationships
    assert seller_mapper.relationships["listings"].back_populates == "seller"
    assert "delete-orphan" in seller_mapper.relationships["listings"].cascade

    listing_mapper = inspect(Listing)
    assert "seller" in listing_mapper.relationships
    assert listing_mapper.relationships["seller"].back_populates == "listings"

    assert "media" in listing_mapper.relationships
    assert listing_mapper.relationships["media"].back_populates == "listing"
    assert "delete-orphan" in listing_mapper.relationships["media"].cascade

    assert "suggestions" in listing_mapper.relationships
    assert listing_mapper.relationships["suggestions"].back_populates == "listing"
    assert "delete-orphan" in listing_mapper.relationships["suggestions"].cascade

    assert "consent" in listing_mapper.relationships
    assert listing_mapper.relationships["consent"].back_populates == "listing"
    assert listing_mapper.relationships["consent"].uselist is False
    assert "delete-orphan" in listing_mapper.relationships["consent"].cascade

    assert "approval" in listing_mapper.relationships
    assert listing_mapper.relationships["approval"].back_populates == "listing"
    assert listing_mapper.relationships["approval"].uselist is False
    assert "delete-orphan" in listing_mapper.relationships["approval"].cascade

    media_mapper = inspect(Media)
    assert "listing" in media_mapper.relationships
    assert media_mapper.relationships["listing"].back_populates == "media"

    consent_mapper = inspect(ListingConsent)
    assert "listing" in consent_mapper.relationships
    assert consent_mapper.relationships["listing"].back_populates == "consent"

    suggestion_mapper = inspect(Suggestion)
    assert "listing" in suggestion_mapper.relationships
    assert suggestion_mapper.relationships["listing"].back_populates == "suggestions"

    approval_mapper = inspect(ListingApproval)
    assert "listing" in approval_mapper.relationships
    assert approval_mapper.relationships["listing"].back_populates == "approval"


@pytest.fixture
def in_memory_session():
    """In-memory SQLite session fixture for verifying ORM behavior without live PostgreSQL."""
    engine = create_engine("sqlite:///:memory:")

    @sa.event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_in_memory_crud_and_defaults(in_memory_session: Session):
    """Test full model instantiation, defaults, and relationships in an in-memory database."""
    # 1. Create seller
    seller = Seller(
        name="Artisan Radha Devi",
        language="hi",
        cluster="Madhubani Cluster",
        ondc_seller_id="ONDC-SELL-IND-9876",
    )
    in_memory_session.add(seller)
    in_memory_session.commit()

    assert isinstance(seller.id, uuid.UUID)
    assert isinstance(seller.created_at, datetime)
    assert isinstance(seller.updated_at, datetime)
    assert seller.name == "Artisan Radha Devi"

    # 2. Create listing
    listing = Listing(
        seller_id=seller.id,
        client_item_id="client-item-001",
    )
    in_memory_session.add(listing)
    in_memory_session.commit()

    assert isinstance(listing.id, uuid.UUID)
    assert listing.state == ListingState.queued
    assert listing.seller.name == "Artisan Radha Devi"

    # 3. Add media
    media_img = Media(
        listing_id=listing.id,
        media_type=MediaType.image,
        original_filename="sample_pottery.jpg",
        storage_path="media/images/sample_pottery.jpg",
        mime_type="image/jpeg",
        file_size_bytes=1048576,
    )
    media_aud = Media(
        listing_id=listing.id,
        media_type=MediaType.audio,
        original_filename="story_note.mp3",
        storage_path="media/audio/story_note.mp3",
        mime_type="audio/mpeg",
        file_size_bytes=524288,
    )
    in_memory_session.add_all([media_img, media_aud])
    in_memory_session.commit()

    assert len(listing.media) == 2
    assert listing.media[0].media_type in (MediaType.image, MediaType.audio)

    # 4. Add consent
    consent = ListingConsent(
        listing_id=listing.id,
        photo_consent=True,
        story_consent=False,
    )
    in_memory_session.add(consent)
    in_memory_session.commit()

    assert listing.consent.photo_consent is True
    assert listing.consent.story_consent is False

    # 5. Add suggestion
    suggestion = Suggestion(
        listing_id=listing.id,
        field="technique",
        value="Terracotta Wheel Handcrafting",
        reason="Detected from voice note description",
    )
    in_memory_session.add(suggestion)
    in_memory_session.commit()

    assert suggestion.approved is None  # pending
    assert len(listing.suggestions) == 1

    # 6. Add approval
    approval = ListingApproval(
        listing_id=listing.id,
        approved=True,
        approved_at=datetime.now(timezone.utc),
    )
    in_memory_session.add(approval)
    in_memory_session.commit()

    assert listing.approval.approved is True
    assert isinstance(listing.approval.approved_at, datetime)

    # 7. Test cascade deletion: deleting seller must remove listing and all dependent records
    in_memory_session.delete(seller)
    in_memory_session.commit()

    assert in_memory_session.query(Listing).count() == 0
    assert in_memory_session.query(Media).count() == 0
    assert in_memory_session.query(ListingConsent).count() == 0
    assert in_memory_session.query(Suggestion).count() == 0
    assert in_memory_session.query(ListingApproval).count() == 0


def test_database_session_generator():
    """Verify get_db dependency functions properly as a request-scoped generator."""
    db_gen = get_db()
    db_session = next(db_gen)
    assert isinstance(db_session, Session)
    # Closing the generator closes the session without error
    with pytest.raises(StopIteration):
        next(db_gen)
