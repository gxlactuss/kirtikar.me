import io
import tempfile
import uuid
from typing import Generator

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import get_current_seller
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.listing import Listing
from app.models.seller import Seller
from app.schemas.enums import ListingState, MediaType
from app.services.listing import transition_listing

client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def setup_api_v1_env() -> Generator[None, None, None]:
    """Provide an isolated in-memory SQLite database and authenticated mock seller for all contract tests."""
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
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    mock_seller_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

    def override_get_db() -> Generator[Session, None, None]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_get_current_seller(db: Session = Depends(get_db)) -> Seller:
        seller = db.query(Seller).filter(Seller.id == mock_seller_id).first()
        if seller is None:
            seller = Seller(
                id=mock_seller_id,
                firebase_uid="firebase-v1-seller",
                name="Artisan Radha Devi",
                language="hi",
                cluster="Madhubani Cluster",
                ondc_seller_id="ONDC-SELL-IND-9876",
                phone_number="+919876543210",
            )
            db.add(seller)
            db.commit()
            db.refresh(seller)
        return seller

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_seller] = override_get_current_seller

    yield

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_seller, None)
    Base.metadata.drop_all(engine)


def test_health_endpoint_intact() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_get_seller_profile() -> None:
    response = client.get("/api/v1/seller", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "name" in data
    assert "language" in data
    assert "cluster" in data
    assert "ondc_seller_id" in data


def test_create_listing() -> None:
    # Valid creation
    response = client.post(
        "/api/v1/listings",
        json={"client_item_id": "mobile-item-123"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["client_item_id"] == "mobile-item-123"
    assert data["state"] == ListingState.queued.value
    assert "id" in data

    # Invalid creation - missing required field
    bad_response = client.post("/api/v1/listings", json={}, headers=AUTH_HEADERS)
    assert bad_response.status_code == 422


def test_get_listing() -> None:
    # Create listing first
    create_res = client.post(
        "/api/v1/listings",
        json={"client_item_id": "item-get-test"},
        headers=AUTH_HEADERS,
    )
    listing_id = create_res.json()["id"]

    response = client.get(f"/api/v1/listings/{listing_id}", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == listing_id
    assert data["client_item_id"] == "item-get-test"
    assert data["state"] in [s.value for s in ListingState]


def test_list_seller_listings() -> None:
    # Seed listings
    client.post("/api/v1/listings", json={"client_item_id": "list-item-001"}, headers=AUTH_HEADERS)
    client.post("/api/v1/listings", json={"client_item_id": "list-item-002"}, headers=AUTH_HEADERS)

    response = client.get("/api/v1/listings", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) >= 2
    for item in data["items"]:
        assert "id" in item
        assert "client_item_id" in item
        assert item["state"] in [s.value for s in ListingState]


def test_media_upload_contract() -> None:
    # Create listing
    create_res = client.post(
        "/api/v1/listings",
        json={"client_item_id": "item-media-contract"},
        headers=AUTH_HEADERS,
    )
    listing_id = create_res.json()["id"]

    with tempfile.TemporaryDirectory() as tmp_dir:
        orig_storage = settings.MEDIA_STORAGE_DIR
        settings.MEDIA_STORAGE_DIR = tmp_dir
        try:
            # Test valid image upload
            file_content = b"fake-image-bytes"
            files = {"file": ("test_art.jpg", io.BytesIO(file_content), "image/jpeg")}
            data = {"media_type": MediaType.image.value}

            response = client.post(
                f"/api/v1/listings/{listing_id}/media", files=files, data=data, headers=AUTH_HEADERS
            )
            assert response.status_code == 200
            res_data = response.json()
            assert res_data["listing_id"] == listing_id
            assert res_data["media_type"] == "image"
            assert res_data["status"] == "uploaded"
            assert "id" in res_data

            # Test valid audio upload
            audio_content = b"fake-audio-bytes"
            files_audio = {"file": ("recording.wav", io.BytesIO(audio_content), "audio/wav")}
            data_audio = {"media_type": MediaType.audio.value}

            response_audio = client.post(
                f"/api/v1/listings/{listing_id}/media", files=files_audio, data=data_audio, headers=AUTH_HEADERS
            )
            assert response_audio.status_code == 200
            assert response_audio.json()["media_type"] == "audio"

            # Test invalid media_type
            bad_files = {"file": ("test.txt", io.BytesIO(b"data"), "text/plain")}
            bad_data = {"media_type": "video"}
            bad_response = client.post(
                f"/api/v1/listings/{listing_id}/media", files=bad_files, data=bad_data, headers=AUTH_HEADERS
            )
            assert bad_response.status_code == 422
        finally:
            settings.MEDIA_STORAGE_DIR = orig_storage


def test_get_listing_status() -> None:
    create_res = client.post(
        "/api/v1/listings",
        json={"client_item_id": "item-status-test"},
        headers=AUTH_HEADERS,
    )
    listing_id = create_res.json()["id"]

    response = client.get(f"/api/v1/listings/{listing_id}/status", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["listing_id"] == listing_id
    assert data["state"] == ListingState.queued.value


def test_get_listing_attention() -> None:
    create_res = client.post(
        "/api/v1/listings",
        json={"client_item_id": "item-attention-test"},
        headers=AUTH_HEADERS,
    )
    listing_id = create_res.json()["id"]

    response = client.get(f"/api/v1/listings/{listing_id}/attention", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["listing_id"] == listing_id
    assert isinstance(data["needs_attention"], bool)
    assert "question" in data
    assert "field" in data


def test_get_listing_readback() -> None:
    create_res = client.post(
        "/api/v1/listings",
        json={"client_item_id": "item-readback-test"},
        headers=AUTH_HEADERS,
    )
    listing_id = create_res.json()["id"]

    # Nothing has been processed, so there is genuinely nothing to read back.
    # This used to answer 200 with a hardcoded Madhubani painting for every
    # listing, whatever the artisan had photographed.
    response = client.get(f"/api/v1/listings/{listing_id}/readback", headers=AUTH_HEADERS)
    assert response.status_code == 409
    assert "processed" in response.json()["detail"].lower()


def test_approve_listing() -> None:
    create_res = client.post(
        "/api/v1/listings",
        json={"client_item_id": "item-approve-test"},
        headers=AUTH_HEADERS,
    )
    listing_id = create_res.json()["id"]

    # Transition to needs_attention to test approval transition -> ready
    from app.services.listing import transition_listing
    from app.db.session import get_db
    db = next(app.dependency_overrides[get_db]())
    listing = db.query(Listing).filter(Listing.id == uuid.UUID(listing_id)).first()
    transition_listing(db, listing, ListingState.processing)
    transition_listing(db, listing, ListingState.needs_attention)

    # Valid approval
    response = client.post(
        f"/api/v1/listings/{listing_id}/approval",
        json={"approved": True},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["listing_id"] == listing_id
    assert data["approved"] is True
    assert data["state"] == ListingState.ready.value

    # Invalid body
    bad_response = client.post(
        f"/api/v1/listings/{listing_id}/approval",
        json={"approved": "not-a-bool"},
        headers=AUTH_HEADERS,
    )
    assert bad_response.status_code == 422


def test_get_listing_suggestions() -> None:
    create_res = client.post(
        "/api/v1/listings",
        json={"client_item_id": "item-suggestions-test"},
        headers=AUTH_HEADERS,
    )
    listing_id = create_res.json()["id"]

    response = client.get(f"/api/v1/listings/{listing_id}/suggestions", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    for item in data["items"]:
        assert "id" in item
        assert "field" in item
        assert "value" in item
        assert "reason" in item


def test_approve_suggestion() -> None:
    create_res = client.post(
        "/api/v1/listings",
        json={"client_item_id": "item-sug-approve-test"},
        headers=AUTH_HEADERS,
    )
    listing_id = create_res.json()["id"]

    response = client.post(
        f"/api/v1/listings/{listing_id}/suggestions/sug-001/approval",
        json={"approved": True},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["listing_id"] == listing_id
    assert data["suggestion_id"] == "sug-001"
    assert data["approved"] is True


def test_record_listing_consent() -> None:
    create_res = client.post(
        "/api/v1/listings",
        json={"client_item_id": "item-consent-test"},
        headers=AUTH_HEADERS,
    )
    listing_id = create_res.json()["id"]

    response = client.post(
        f"/api/v1/listings/{listing_id}/consent",
        json={"photo": True, "story": True},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["listing_id"] == listing_id
    assert data["photo"] is True
    assert data["story"] is True
    assert data["ready_to_publish"] is True

    # Test invalid consent body
    bad_response = client.post(
        f"/api/v1/listings/{listing_id}/consent",
        json={"photo": "yes"},
        headers=AUTH_HEADERS,
    )
    assert bad_response.status_code == 422


def test_publish_listing() -> None:
    create_res = client.post(
        "/api/v1/listings",
        json={"client_item_id": "item-publish-test"},
        headers=AUTH_HEADERS,
    )
    listing_id = create_res.json()["id"]

    # Transition listing to ready state before publishing
    from app.services.listing import transition_listing
    from app.db.session import get_db
    db = next(app.dependency_overrides[get_db]())
    listing = db.query(Listing).filter(Listing.id == uuid.UUID(listing_id)).first()
    transition_listing(db, listing, ListingState.processing)
    transition_listing(db, listing, ListingState.ready)

    response = client.post(f"/api/v1/listings/{listing_id}/publish", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["listing_id"] == listing_id
    assert data["state"] == ListingState.published.value
    assert "preview_url" in data


def test_get_listing_preview() -> None:
    create_res = client.post(
        "/api/v1/listings",
        json={"client_item_id": "item-preview-test"},
        headers=AUTH_HEADERS,
    )
    listing_id = create_res.json()["id"]

    response = client.get(f"/api/v1/listings/{listing_id}/preview", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["listing_id"] == listing_id
    assert "title" in data
    assert "description" in data
    assert "price" in data
    assert "image_urls" in data
    assert isinstance(data["image_urls"], list)


def test_openapi_schema_contains_all_routes() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    paths = schema["paths"]
    # Check root health check
    assert "/health" in paths

    # Check all 14 v1 endpoint paths
    expected_paths = [
        "/api/v1/seller",
        "/api/v1/listings",
        "/api/v1/listings/{listing_id}",
        "/api/v1/listings/{listing_id}/media",
        "/api/v1/listings/{listing_id}/status",
        "/api/v1/listings/{listing_id}/attention",
        "/api/v1/listings/{listing_id}/readback",
        "/api/v1/listings/{listing_id}/approval",
        "/api/v1/listings/{listing_id}/suggestions",
        "/api/v1/listings/{listing_id}/suggestions/{suggestion_id}/approval",
        "/api/v1/listings/{listing_id}/consent",
        "/api/v1/listings/{listing_id}/publish",
        "/api/v1/listings/{listing_id}/preview",
    ]

    for ep in expected_paths:
        assert ep in paths, f"Path {ep} missing from OpenAPI schema"
