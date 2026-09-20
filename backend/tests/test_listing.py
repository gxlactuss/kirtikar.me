"""Comprehensive unit and integration test suite for real listing persistence and state machine."""
import io
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.listing import Listing
from app.models.media import Media
from app.models.seller import Seller
from app.schemas.enums import ListingState, MediaType
from app.services.listing import (
    InvalidStateTransitionError,
    ListingNotFoundError,
    create_or_get_listing,
    get_listing_for_seller,
    list_seller_listings,
    transition_listing,
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
def client(test_engine) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with overridden get_db bound to the test database engine."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db() -> Generator[Session, None, None]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="function")
def sellers_and_auth(test_db: Session):
    """Create two distinct Seller entities and generate valid application JWT tokens."""
    seller_a = Seller(
        id=uuid.uuid4(),
        firebase_uid="firebase-user-a",
        phone_number="+919876543210",
        name="Artisan Radha Devi",
        language="hi",
        cluster="Madhubani Cluster",
        ondc_seller_id="ONDC-IND-1001",
    )
    seller_b = Seller(
        id=uuid.uuid4(),
        firebase_uid="firebase-user-b",
        phone_number="+919876543211",
        name="Artisan Mohan Lal",
        language="en",
        cluster="Varanasi Weavers",
        ondc_seller_id="ONDC-IND-1002",
    )
    test_db.add_all([seller_a, seller_b])
    test_db.commit()
    test_db.refresh(seller_a)
    test_db.refresh(seller_b)

    token_a = create_access_token(seller_id=seller_a.id)
    token_b = create_access_token(seller_id=seller_b.id)

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    return (seller_a, headers_a), (seller_b, headers_b)


def test_authenticated_seller_creates_persisted_listing(client: TestClient, test_db: Session, sellers_and_auth):
    """Verify authenticated seller can create a listing, which is stored in DB with queued state and UUID."""
    (seller_a, headers_a), _ = sellers_and_auth

    payload = {"client_item_id": "mobile-capture-001"}
    response = client.post("/api/v1/listings", json=payload, headers=headers_a)

    assert response.status_code == 200
    data = response.json()
    assert data["client_item_id"] == "mobile-capture-001"
    assert data["state"] == ListingState.queued.value
    assert "id" in data

    listing_id = uuid.UUID(data["id"])

    # Query DB to confirm persistent record
    db_listing = test_db.query(Listing).filter(Listing.id == listing_id).first()
    assert db_listing is not None
    assert db_listing.seller_id == seller_a.id
    assert db_listing.client_item_id == "mobile-capture-001"
    assert db_listing.state == ListingState.queued
    assert isinstance(db_listing.created_at, datetime)
    assert isinstance(db_listing.updated_at, datetime)
    assert Listing.created_at.type.timezone is True
    assert Listing.updated_at.type.timezone is True


def test_unauthenticated_listing_creation_rejected(client: TestClient):
    """Verify listing creation without token returns 401 Unauthorized."""
    response = client.post("/api/v1/listings", json={"client_item_id": "item-unauth"})
    assert response.status_code == 401


def test_client_cannot_supply_seller_id_or_other_fields(client: TestClient, sellers_and_auth):
    """Verify client cannot inject seller_id or state in the request body (extra='forbid')."""
    _, (_, headers_b) = sellers_and_auth

    # Attempt to pass forbidden seller_id
    response = client.post(
        "/api/v1/listings",
        json={"client_item_id": "item-001", "seller_id": str(uuid.uuid4())},
        headers=headers_b,
    )
    assert response.status_code == 422


def test_seller_can_retrieve_own_listing(client: TestClient, sellers_and_auth):
    """Verify seller can retrieve their own listing by server identifier."""
    (seller_a, headers_a), _ = sellers_and_auth

    create_res = client.post("/api/v1/listings", json={"client_item_id": "item-own"}, headers=headers_a)
    listing_id = create_res.json()["id"]

    response = client.get(f"/api/v1/listings/{listing_id}", headers=headers_a)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == listing_id
    assert data["client_item_id"] == "item-own"
    assert data["state"] == ListingState.queued.value


def test_seller_cannot_retrieve_another_sellers_listing(client: TestClient, sellers_and_auth):
    """Verify seller B cannot access seller A's listing (returns 404 Not Found to prevent leaking existence)."""
    (seller_a, headers_a), (seller_b, headers_b) = sellers_and_auth

    create_res = client.post("/api/v1/listings", json={"client_item_id": "seller-a-item"}, headers=headers_a)
    listing_id = create_res.json()["id"]

    response = client.get(f"/api/v1/listings/{listing_id}", headers=headers_b)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_nonexistent_or_malformed_listing_id_returns_404(client: TestClient, sellers_and_auth):
    """Verify nonexistent UUID or malformed listing identifier returns 404."""
    (seller_a, headers_a), _ = sellers_and_auth

    random_id = str(uuid.uuid4())
    res_random = client.get(f"/api/v1/listings/{random_id}", headers=headers_a)
    assert res_random.status_code == 404

    res_malformed = client.get("/api/v1/listings/not-a-valid-uuid", headers=headers_a)
    assert res_malformed.status_code == 404


def test_list_seller_listings_returns_only_authenticated_sellers_listings(client: TestClient, sellers_and_auth):
    """Verify GET /listings returns only listings belonging to current seller, ordered newest first."""
    (seller_a, headers_a), (seller_b, headers_b) = sellers_and_auth

    # Create 2 listings for Seller A
    res_a1 = client.post("/api/v1/listings", json={"client_item_id": "a-item-1"}, headers=headers_a)
    res_a2 = client.post("/api/v1/listings", json={"client_item_id": "a-item-2"}, headers=headers_a)

    # Create 1 listing for Seller B
    res_b1 = client.post("/api/v1/listings", json={"client_item_id": "b-item-1"}, headers=headers_b)

    # Check Seller A's listing view
    list_a = client.get("/api/v1/listings", headers=headers_a)
    assert list_a.status_code == 200
    items_a = list_a.json()["items"]
    assert len(items_a) == 2
    ids_a = [item["id"] for item in items_a]
    assert res_a1.json()["id"] in ids_a
    assert res_a2.json()["id"] in ids_a
    assert res_b1.json()["id"] not in ids_a
    # Newest first
    assert ids_a[0] == res_a2.json()["id"]

    # Check Seller B's listing view
    list_b = client.get("/api/v1/listings", headers=headers_b)
    assert list_b.status_code == 200
    items_b = list_b.json()["items"]
    assert len(items_b) == 1
    assert items_b[0]["id"] == res_b1.json()["id"]


def test_same_seller_same_client_item_id_idempotent(client: TestClient, test_db: Session, sellers_and_auth):
    """Verify identical repeated creation requests from same seller return existing listing deterministically."""
    (seller_a, headers_a), _ = sellers_and_auth

    res1 = client.post("/api/v1/listings", json={"client_item_id": "idemp-001"}, headers=headers_a)
    assert res1.status_code == 200
    id1 = res1.json()["id"]

    res2 = client.post("/api/v1/listings", json={"client_item_id": "idemp-001"}, headers=headers_a)
    assert res2.status_code == 200
    id2 = res2.json()["id"]

    assert id1 == id2

    # Database has only 1 row
    count = (
        test_db.query(Listing)
        .filter(Listing.seller_id == seller_a.id, Listing.client_item_id == "idemp-001")
        .count()
    )
    assert count == 1


def test_different_sellers_same_client_item_id_allowed(client: TestClient, sellers_and_auth):
    """Verify different sellers can use the same client_item_id without conflict."""
    (seller_a, headers_a), (seller_b, headers_b) = sellers_and_auth

    res_a = client.post("/api/v1/listings", json={"client_item_id": "mobile-capture-x"}, headers=headers_a)
    assert res_a.status_code == 200

    res_b = client.post("/api/v1/listings", json={"client_item_id": "mobile-capture-x"}, headers=headers_b)
    assert res_b.status_code == 200

    assert res_a.json()["id"] != res_b.json()["id"]


@pytest.mark.parametrize(
    "initial,target",
    [
        (ListingState.queued, ListingState.processing),
        (ListingState.processing, ListingState.needs_attention),
        (ListingState.processing, ListingState.ready),
        (ListingState.needs_attention, ListingState.processing),
        (ListingState.needs_attention, ListingState.ready),
        (ListingState.ready, ListingState.published),
        (ListingState.ready, ListingState.needs_attention),
    ],
)
def test_valid_state_transitions(test_db: Session, sellers_and_auth, initial: ListingState, target: ListingState):
    """Verify all defined valid state transitions succeed and update timestamps."""
    (seller_a, _), _ = sellers_and_auth

    listing = Listing(
        seller_id=seller_a.id,
        client_item_id=f"trans-{initial.value}-{target.value}",
        state=initial,
    )
    test_db.add(listing)
    test_db.commit()
    test_db.refresh(listing)

    orig_updated_at = listing.updated_at
    updated = transition_listing(test_db, listing, target)

    assert updated.state == target
    assert updated.updated_at >= orig_updated_at


@pytest.mark.parametrize(
    "initial,invalid_target",
    [
        (ListingState.queued, ListingState.published),
        (ListingState.queued, ListingState.ready),
        (ListingState.queued, ListingState.needs_attention),
        (ListingState.processing, ListingState.queued),
        (ListingState.processing, ListingState.published),
        (ListingState.needs_attention, ListingState.queued),
        (ListingState.needs_attention, ListingState.published),
        (ListingState.ready, ListingState.queued),
        (ListingState.ready, ListingState.processing),
        (ListingState.published, ListingState.queued),
        (ListingState.published, ListingState.processing),
        (ListingState.published, ListingState.needs_attention),
        (ListingState.published, ListingState.ready),
    ],
)
def test_invalid_state_transitions_rejected(
    test_db: Session, sellers_and_auth, initial: ListingState, invalid_target: ListingState
):
    """Verify illegal transitions are rejected with InvalidStateTransitionError / 400."""
    (seller_a, _), _ = sellers_and_auth

    listing = Listing(
        seller_id=seller_a.id,
        client_item_id=f"invalid-{initial.value}-{invalid_target.value}",
        state=initial,
    )
    test_db.add(listing)
    test_db.commit()

    with pytest.raises(InvalidStateTransitionError):
        transition_listing(test_db, listing, invalid_target)


def test_published_is_terminal_state(test_db: Session, sellers_and_auth):
    """Verify published state cannot transition to any other lifecycle state."""
    (seller_a, _), _ = sellers_and_auth

    listing = Listing(
        seller_id=seller_a.id,
        client_item_id="terminal-test",
        state=ListingState.published,
    )
    test_db.add(listing)
    test_db.commit()

    for state in [
        ListingState.queued,
        ListingState.processing,
        ListingState.needs_attention,
        ListingState.ready,
    ]:
        with pytest.raises(InvalidStateTransitionError):
            transition_listing(test_db, listing, state)


def test_persisted_state_survives_fresh_db_session(test_engine, sellers_and_auth):
    """Verify state transition is genuinely persisted in the database across sessions."""
    (seller_a, _), _ = sellers_and_auth
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Session 1: Create and transition
    sess1 = SessionLocal()
    listing = Listing(
        seller_id=seller_a.id,
        client_item_id="survive-session",
        state=ListingState.queued,
    )
    sess1.add(listing)
    sess1.commit()
    listing_id = listing.id
    transition_listing(sess1, listing, ListingState.processing)
    sess1.close()

    # Session 2: Read from fresh session
    sess2 = SessionLocal()
    reloaded = sess2.query(Listing).filter(Listing.id == listing_id).first()
    assert reloaded is not None
    assert reloaded.state == ListingState.processing
    sess2.close()


def test_status_endpoint_returns_actual_db_state(client: TestClient, test_db: Session, sellers_and_auth):
    """Verify GET /listings/{id}/status returns the real current DB state."""
    (seller_a, headers_a), _ = sellers_and_auth

    create_res = client.post("/api/v1/listings", json={"client_item_id": "status-item"}, headers=headers_a)
    listing_id = create_res.json()["id"]

    # Initial state
    res1 = client.get(f"/api/v1/listings/{listing_id}/status", headers=headers_a)
    assert res1.status_code == 200
    assert res1.json()["state"] == ListingState.queued.value

    # Update in DB to processing
    listing = test_db.query(Listing).filter(Listing.id == uuid.UUID(listing_id)).first()
    transition_listing(test_db, listing, ListingState.processing)

    res2 = client.get(f"/api/v1/listings/{listing_id}/status", headers=headers_a)
    assert res2.status_code == 200
    assert res2.json()["state"] == ListingState.processing.value


def test_approval_endpoint_state_transitions(client: TestClient, test_db: Session, sellers_and_auth):
    """Verify POST /listings/{id}/approval enforces state transitions."""
    (seller_a, headers_a), _ = sellers_and_auth

    create_res = client.post("/api/v1/listings", json={"client_item_id": "approval-item"}, headers=headers_a)
    listing_id = create_res.json()["id"]
    listing = test_db.query(Listing).filter(Listing.id == uuid.UUID(listing_id)).first()

    # In queued state, approval cannot jump to ready
    bad_approve = client.post(
        f"/api/v1/listings/{listing_id}/approval",
        json={"approved": True},
        headers=headers_a,
    )
    assert bad_approve.status_code == 400

    # Advance to needs_attention
    transition_listing(test_db, listing, ListingState.processing)
    transition_listing(test_db, listing, ListingState.needs_attention)

    # Approve from needs_attention -> ready
    good_approve = client.post(
        f"/api/v1/listings/{listing_id}/approval",
        json={"approved": True},
        headers=headers_a,
    )
    assert good_approve.status_code == 200
    assert good_approve.json()["state"] == ListingState.ready.value

    # Rejection from ready -> needs_attention
    reject_res = client.post(
        f"/api/v1/listings/{listing_id}/approval",
        json={"approved": False},
        headers=headers_a,
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["state"] == ListingState.needs_attention.value


def test_publish_endpoint_state_enforcement(client: TestClient, test_db: Session, sellers_and_auth):
    """Verify POST /listings/{id}/publish only succeeds when listing is in ready state."""
    (seller_a, headers_a), _ = sellers_and_auth

    create_res = client.post("/api/v1/listings", json={"client_item_id": "publish-item"}, headers=headers_a)
    listing_id = create_res.json()["id"]
    listing = test_db.query(Listing).filter(Listing.id == uuid.UUID(listing_id)).first()

    # From queued -> 400
    res_queued = client.post(f"/api/v1/listings/{listing_id}/publish", headers=headers_a)
    assert res_queued.status_code == 400

    # From processing -> 400
    transition_listing(test_db, listing, ListingState.processing)
    res_proc = client.post(f"/api/v1/listings/{listing_id}/publish", headers=headers_a)
    assert res_proc.status_code == 400

    # From needs_attention -> 400
    transition_listing(test_db, listing, ListingState.needs_attention)
    res_att = client.post(f"/api/v1/listings/{listing_id}/publish", headers=headers_a)
    assert res_att.status_code == 400

    # From ready -> 200 Published!
    transition_listing(test_db, listing, ListingState.ready)
    res_ready = client.post(f"/api/v1/listings/{listing_id}/publish", headers=headers_a)
    assert res_ready.status_code == 200
    assert res_ready.json()["state"] == ListingState.published.value

    # Verify DB state is now published
    test_db.refresh(listing)
    assert listing.state == ListingState.published


def test_downstream_endpoints_seller_ownership(client: TestClient, sellers_and_auth):
    """Verify all downstream listing operations return 404 when accessed by non-owner."""
    (seller_a, headers_a), (seller_b, headers_b) = sellers_and_auth

    create_res = client.post("/api/v1/listings", json={"client_item_id": "downstream-owner"}, headers=headers_a)
    listing_id = create_res.json()["id"]

    # Seller B attempts downstream actions on Seller A's listing
    assert client.get(f"/api/v1/listings/{listing_id}/attention", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/listings/{listing_id}/readback", headers=headers_b).status_code == 404
    assert (
        client.post(
            f"/api/v1/listings/{listing_id}/approval", json={"approved": True}, headers=headers_b
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/listings/{listing_id}/suggestions", headers=headers_b).status_code == 404
    assert (
        client.post(
            f"/api/v1/listings/{listing_id}/suggestions/sug-001/approval",
            json={"approved": True},
            headers=headers_b,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/listings/{listing_id}/consent", json={"photo": True, "story": True}, headers=headers_b
        ).status_code
        == 404
    )
    assert client.post(f"/api/v1/listings/{listing_id}/publish", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/listings/{listing_id}/preview", headers=headers_b).status_code == 404


def test_media_upload_to_real_persisted_listing(client: TestClient, test_db: Session, sellers_and_auth):
    """Verify uploading media to a real persisted listing connects to the DB Media record and enforces ownership."""
    (seller_a, headers_a), (seller_b, headers_b) = sellers_and_auth

    # Create real listing
    create_res = client.post("/api/v1/listings", json={"client_item_id": "media-real-listing"}, headers=headers_a)
    listing_id = create_res.json()["id"]

    with tempfile.TemporaryDirectory() as tmp_dir:
        orig_storage = settings.MEDIA_STORAGE_DIR
        settings.MEDIA_STORAGE_DIR = tmp_dir
        try:
            # Seller A uploads media to their real listing
            image_bytes = b"real-listing-media-bytes"
            files = {"file": ("painting.png", io.BytesIO(image_bytes), "image/png")}
            data = {"media_type": MediaType.image.value}

            upload_res = client.post(
                f"/api/v1/listings/{listing_id}/media", files=files, data=data, headers=headers_a
            )
            assert upload_res.status_code == 200
            media_data = upload_res.json()
            media_uuid = uuid.UUID(media_data["id"])

            # Verify Media record in DB
            db_media = test_db.query(Media).filter(Media.id == media_uuid).first()
            assert db_media is not None
            assert db_media.listing_id == uuid.UUID(listing_id)
            assert db_media.media_type == MediaType.image
            assert db_media.original_filename == "painting.png"
            assert db_media.file_size_bytes == len(image_bytes)

            # Seller B attempts to upload media to Seller A's real listing -> 403 Forbidden
            files_b = {"file": ("hijack.png", io.BytesIO(b"hijack"), "image/png")}
            data_b = {"media_type": MediaType.image.value}
            upload_b = client.post(
                f"/api/v1/listings/{listing_id}/media", files=files_b, data=data_b, headers=headers_b
            )
            assert upload_b.status_code == 403
            assert "does not belong" in upload_b.json()["detail"].lower()
        finally:
            settings.MEDIA_STORAGE_DIR = orig_storage


def test_seller_can_delete_their_listing(client: TestClient, test_db: Session, sellers_and_auth):
    """A deleted listing is gone from the database and from the seller's list."""
    (_, headers_a), _ = sellers_and_auth

    created = client.post("/api/v1/listings", json={"client_item_id": "to-delete"}, headers=headers_a)
    assert created.status_code == 200
    listing_id = created.json()["id"]

    response = client.delete(f"/api/v1/listings/{listing_id}", headers=headers_a)
    assert response.status_code == 204

    assert test_db.query(Listing).filter(Listing.id == uuid.UUID(listing_id)).first() is None

    listed = client.get("/api/v1/listings", headers=headers_a)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == []


def test_deleting_the_same_listing_twice_succeeds(client: TestClient, sellers_and_auth):
    """A phone retrying a delete it already made must not be told the listing is missing."""
    (_, headers_a), _ = sellers_and_auth

    created = client.post("/api/v1/listings", json={"client_item_id": "delete-twice"}, headers=headers_a)
    listing_id = created.json()["id"]

    assert client.delete(f"/api/v1/listings/{listing_id}", headers=headers_a).status_code == 204
    assert client.delete(f"/api/v1/listings/{listing_id}", headers=headers_a).status_code == 204


def test_seller_cannot_delete_another_sellers_listing(client: TestClient, test_db: Session, sellers_and_auth):
    """Ownership is enforced: B deleting A's listing must leave it untouched."""
    (_, headers_a), (_, headers_b) = sellers_and_auth

    created = client.post("/api/v1/listings", json={"client_item_id": "owned-by-a"}, headers=headers_a)
    listing_id = created.json()["id"]

    # B is told nothing about a listing that is not theirs, and it survives.
    assert client.delete(f"/api/v1/listings/{listing_id}", headers=headers_b).status_code == 204
    assert test_db.query(Listing).filter(Listing.id == uuid.UUID(listing_id)).first() is not None

    listed = client.get("/api/v1/listings", headers=headers_a)
    assert [item["id"] for item in listed.json()["items"]] == [listing_id]


def test_unauthenticated_delete_rejected(client: TestClient, sellers_and_auth):
    """Deleting without a token is refused."""
    (_, headers_a), _ = sellers_and_auth
    created = client.post("/api/v1/listings", json={"client_item_id": "needs-auth"}, headers=headers_a)
    listing_id = created.json()["id"]

    assert client.delete(f"/api/v1/listings/{listing_id}").status_code == 401


def _ready_listing(client: TestClient, test_db: Session, headers, client_item_id: str):
    """A listing with a result row and one open suggestion about its origin."""
    from app.models.listing_result import ListingResult
    from app.models.suggestion import Suggestion as SuggestionModel

    created = client.post(
        "/api/v1/listings", json={"client_item_id": client_item_id}, headers=headers
    )
    listing_id = created.json()["id"]

    test_db.add(ListingResult(listing_id=uuid.UUID(listing_id), title="Clay pot"))
    suggestion = SuggestionModel(
        listing_id=uuid.UUID(listing_id),
        field="origin",
        value="origin",
        reason="The voice note did not mention where it was made.",
        approved=None,
    )
    test_db.add(suggestion)
    test_db.commit()
    test_db.refresh(suggestion)
    return listing_id, str(suggestion.id)


def test_suggestion_names_the_field_it_is_about(client: TestClient, test_db: Session, sellers_and_auth):
    """The app needs the field name to know which input to open."""
    (_, headers_a), _ = sellers_and_auth
    listing_id, _ = _ready_listing(client, test_db, headers_a, "names-field")

    body = client.get(f"/api/v1/listings/{listing_id}", headers=headers_a).json()

    assert body["suggestions"][0]["field"] == "origin"


def test_patch_writes_a_correction_onto_the_fact_sheet(client: TestClient, test_db: Session, sellers_and_auth):
    """A corrected field is stored and comes back in the fact sheet."""
    (_, headers_a), _ = sellers_and_auth
    listing_id, _ = _ready_listing(client, test_db, headers_a, "patch-origin")

    response = client.patch(
        f"/api/v1/listings/{listing_id}", json={"origin": "Jaipur"}, headers=headers_a
    )

    assert response.status_code == 200
    assert response.json()["fact_sheet"]["origin"] == "Jaipur"

    fetched = client.get(f"/api/v1/listings/{listing_id}", headers=headers_a)
    assert fetched.json()["fact_sheet"]["origin"] == "Jaipur"


def test_patch_settles_the_suggestion_it_answers(client: TestClient, test_db: Session, sellers_and_auth):
    """Filling a gap must stop the same gap being asked again."""
    (_, headers_a), _ = sellers_and_auth
    listing_id, _ = _ready_listing(client, test_db, headers_a, "patch-settles")

    client.patch(
        f"/api/v1/listings/{listing_id}", json={"origin": "Jaipur"}, headers=headers_a
    )

    body = client.get(f"/api/v1/listings/{listing_id}", headers=headers_a).json()
    assert body["suggestions"][0]["approved"] is True


def test_patch_refuses_a_field_it_cannot_store(client: TestClient, test_db: Session, sellers_and_auth):
    """Silently dropping a correction would tell the artisan a lie."""
    (_, headers_a), _ = sellers_and_auth
    listing_id, _ = _ready_listing(client, test_db, headers_a, "patch-unknown")

    response = client.patch(
        f"/api/v1/listings/{listing_id}",
        json={"imageUrls": ["a.jpg"]},
        headers=headers_a,
    )

    assert response.status_code == 400
    assert "imageUrls" in response.json()["detail"]


def test_patch_price_is_stored_in_paise(client: TestClient, test_db: Session, sellers_and_auth):
    """The app sends money in paise; it must not be reinterpreted."""
    (_, headers_a), _ = sellers_and_auth
    listing_id, _ = _ready_listing(client, test_db, headers_a, "patch-price")

    response = client.patch(
        f"/api/v1/listings/{listing_id}", json={"price": 45000}, headers=headers_a
    )

    assert response.json()["fact_sheet"]["price_in_paise"] == 45000


def test_answer_stores_the_spoken_value_and_the_recording(client: TestClient, test_db: Session, sellers_and_auth):
    """A spoken answer reaches the fact sheet, and the audio is kept."""
    from app.models.media import Media

    (_, headers_a), _ = sellers_and_auth
    listing_id, _ = _ready_listing(client, test_db, headers_a, "answer-origin")

    response = client.post(
        f"/api/v1/listings/{listing_id}/answer",
        files={"voiceReply": ("reply.m4a", b"fake audio bytes", "audio/mp4")},
        data={"field": "origin", "transcript": "Jaipur"},
        headers=headers_a,
    )

    assert response.status_code == 200, response.text
    assert response.json()["fact_sheet"]["origin"] == "Jaipur"

    kept = test_db.query(Media).filter(Media.listing_id == uuid.UUID(listing_id)).all()
    assert len(kept) == 1


def test_answer_settles_the_suggestion(client: TestClient, test_db: Session, sellers_and_auth):
    """The gap the answer filled is not asked again."""
    (_, headers_a), _ = sellers_and_auth
    listing_id, _ = _ready_listing(client, test_db, headers_a, "answer-settles")

    client.post(
        f"/api/v1/listings/{listing_id}/answer",
        files={"voiceReply": ("reply.m4a", b"fake audio bytes", "audio/mp4")},
        data={"field": "origin", "transcript": "Jaipur"},
        headers=headers_a,
    )

    body = client.get(f"/api/v1/listings/{listing_id}", headers=headers_a).json()
    assert body["suggestions"][0]["approved"] is True


def test_suggestion_approval_is_persisted(client: TestClient, test_db: Session, sellers_and_auth):
    """Approval used to be echoed back and stored nowhere."""
    (_, headers_a), _ = sellers_and_auth
    listing_id, suggestion_id = _ready_listing(client, test_db, headers_a, "approval")

    response = client.post(
        f"/api/v1/listings/{listing_id}/suggestions/{suggestion_id}/approval",
        json={"approved": False},
        headers=headers_a,
    )
    assert response.status_code == 200

    body = client.get(f"/api/v1/listings/{listing_id}", headers=headers_a).json()
    assert body["suggestions"][0]["approved"] is False


def test_another_seller_cannot_correct_your_listing(client: TestClient, test_db: Session, sellers_and_auth):
    """Ownership is enforced on the write paths too."""
    (_, headers_a), (_, headers_b) = sellers_and_auth
    listing_id, _ = _ready_listing(client, test_db, headers_a, "owned")

    assert client.patch(
        f"/api/v1/listings/{listing_id}", json={"origin": "Nowhere"}, headers=headers_b
    ).status_code == 404

    body = client.get(f"/api/v1/listings/{listing_id}", headers=headers_a).json()
    assert body["fact_sheet"]["origin"] is None
