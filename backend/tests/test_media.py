"""Comprehensive test suite for local media upload and storage layer."""
import io
import uuid
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest
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
def media_client(test_engine) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with overridden get_db bound to the test database engine."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db() -> Generator[Session, None, None]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="function")
def isolated_storage(tmp_path, monkeypatch):
    """Isolate media storage directory to a temporary pytest path."""
    storage_dir = tmp_path / "media_storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "MEDIA_STORAGE_DIR", str(storage_dir))
    return storage_dir


@pytest.fixture(scope="function")
def seller_and_auth(test_db: Session):
    """Create a test Seller entity and generate a valid Bearer token."""
    seller = Seller(
        id=uuid.uuid4(),
        firebase_uid="firebase-user-artisan-1",
        phone_number="+919876543210",
        name="Artisan Radha Devi",
        language="hi",
        cluster="Madhubani Cluster",
        ondc_seller_id="ONDC-IND-1001",
    )
    test_db.add(seller)
    test_db.commit()
    test_db.refresh(seller)

    token = create_access_token(seller_id=seller.id)
    headers = {"Authorization": f"Bearer {token}"}
    return seller, headers


def test_valid_image_upload_success_and_disk_storage(
    media_client: TestClient,
    isolated_storage: Path,
    seller_and_auth,
):
    """Verify valid image upload succeeds, returns expected contract, and stores file on disk."""
    seller, headers = seller_and_auth
    listing_id = "lst-stub-101"
    image_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"

    files = {"file": ("madhubani_painting.jpg", io.BytesIO(image_bytes), "image/jpeg")}
    data = {"media_type": MediaType.image.value}

    response = media_client.post(f"/api/v1/listings/{listing_id}/media", files=files, data=data, headers=headers)

    assert response.status_code == 200
    res = response.json()
    assert res["listing_id"] == listing_id
    assert res["media_type"] == "image"
    assert res["status"] == "uploaded"
    assert "id" in res

    # Verify server-controlled UUID filename created on disk
    media_id = res["id"]
    expected_file = isolated_storage / listing_id / f"{media_id}.jpg"
    assert expected_file.is_file()
    assert expected_file.read_bytes() == image_bytes


def test_valid_audio_upload_success_and_disk_storage(
    media_client: TestClient,
    isolated_storage: Path,
    seller_and_auth,
):
    """Verify valid audio upload succeeds, returns expected contract, and stores file on disk."""
    seller, headers = seller_and_auth
    listing_id = "lst-stub-102"
    audio_bytes = b"RIFF....WAVEfmt ....data...."

    files = {"file": ("artisan_story.wav", io.BytesIO(audio_bytes), "audio/wav")}
    data = {"media_type": MediaType.audio.value}

    response = media_client.post(f"/api/v1/listings/{listing_id}/media", files=files, data=data, headers=headers)

    assert response.status_code == 200
    res = response.json()
    assert res["listing_id"] == listing_id
    assert res["media_type"] == "audio"
    assert res["status"] == "uploaded"
    assert "id" in res

    media_id = res["id"]
    expected_file = isolated_storage / listing_id / f"{media_id}.wav"
    assert expected_file.is_file()
    assert expected_file.read_bytes() == audio_bytes


@pytest.mark.parametrize(
    "filename,mime_type,expected_ext,media_type",
    [
        ("photo.png", "image/png", ".png", MediaType.image),
        ("photo.webp", "image/webp", ".webp", MediaType.image),
        ("photo.jpeg", "image/jpeg", ".jpg", MediaType.image),
        ("voice.mp3", "audio/mpeg", ".mp3", MediaType.audio),
        ("voice.m4a", "audio/m4a", ".m4a", MediaType.audio),
        ("voice.ogg", "audio/ogg", ".ogg", MediaType.audio),
    ],
)
def test_various_supported_formats(
    media_client: TestClient,
    isolated_storage: Path,
    seller_and_auth,
    filename: str,
    mime_type: str,
    expected_ext: str,
    media_type: MediaType,
):
    """Verify all supported MIME types for images and audio are accepted and stored correctly."""
    _, headers = seller_and_auth
    listing_id = "lst-format-test"
    content = b"valid-media-payload-bytes"

    files = {"file": (filename, io.BytesIO(content), mime_type)}
    data = {"media_type": media_type.value}

    response = media_client.post(f"/api/v1/listings/{listing_id}/media", files=files, data=data, headers=headers)
    assert response.status_code == 200
    res = response.json()
    stored_path = isolated_storage / listing_id / f"{res['id']}{expected_ext}"
    assert stored_path.is_file()


def test_server_controlled_filename_prevents_collision(
    media_client: TestClient,
    isolated_storage: Path,
    seller_and_auth,
):
    """Verify multiple uploads with identical client filenames receive unique server-controlled UUIDs."""
    _, headers = seller_and_auth
    listing_id = "lst-collision-test"

    files1 = {"file": ("item.png", io.BytesIO(b"content-version-1"), "image/png")}
    data = {"media_type": MediaType.image.value}
    resp1 = media_client.post(f"/api/v1/listings/{listing_id}/media", files=files1, data=data, headers=headers)
    assert resp1.status_code == 200
    id1 = resp1.json()["id"]

    files2 = {"file": ("item.png", io.BytesIO(b"content-version-2"), "image/png")}
    resp2 = media_client.post(f"/api/v1/listings/{listing_id}/media", files=files2, data=data, headers=headers)
    assert resp2.status_code == 200
    id2 = resp2.json()["id"]

    assert id1 != id2
    file1 = isolated_storage / listing_id / f"{id1}.png"
    file2 = isolated_storage / listing_id / f"{id2}.png"
    assert file1.is_file()
    assert file2.is_file()
    assert file1.read_bytes() == b"content-version-1"
    assert file2.read_bytes() == b"content-version-2"


def test_client_filename_path_traversal_is_neutralized(
    media_client: TestClient,
    isolated_storage: Path,
    seller_and_auth,
):
    """Verify directory traversal in client filename (e.g. ../../etc/passwd.jpg) cannot escape storage dir."""
    _, headers = seller_and_auth
    listing_id = "lst-traversal-test"
    malicious_filename = "../../../../etc/passwd.jpg"
    payload = b"traversal-test-payload"

    files = {"file": (malicious_filename, io.BytesIO(payload), "image/jpeg")}
    data = {"media_type": MediaType.image.value}

    response = media_client.post(f"/api/v1/listings/{listing_id}/media", files=files, data=data, headers=headers)
    assert response.status_code == 200
    media_id = response.json()["id"]

    # File must be stored strictly within isolated_storage / listing_id
    stored_file = isolated_storage / listing_id / f"{media_id}.jpg"
    assert stored_file.is_file()
    assert stored_file.read_bytes() == payload

    # Ensure no file was created at root or parent
    assert not (isolated_storage.parent / "passwd.jpg").exists()


@pytest.mark.parametrize("bad_listing_id", ["../../evil", "lst/slash", "lst..dot", "lst space"])
def test_malicious_listing_id_path_traversal_rejected(
    media_client: TestClient,
    isolated_storage: Path,
    seller_and_auth,
    bad_listing_id: str,
):
    """Verify invalid listing identifiers with directory traversal attempts are rejected with 400."""
    _, headers = seller_and_auth
    files = {"file": ("photo.jpg", io.BytesIO(b"bytes"), "image/jpeg")}
    data = {"media_type": MediaType.image.value}

    response = media_client.post(f"/api/v1/listings/{bad_listing_id}/media", files=files, data=data, headers=headers)
    # 400 Bad Request or 404 from route matching
    assert response.status_code in [400, 404]


def test_unsupported_mime_type_rejected(
    media_client: TestClient,
    seller_and_auth,
):
    """Verify unsupported MIME types return 415 Unsupported Media Type."""
    _, headers = seller_and_auth
    listing_id = "lst-unsupported"

    # PDF upload for image
    files_pdf = {"file": ("document.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}
    res_pdf = media_client.post(
        f"/api/v1/listings/{listing_id}/media",
        files=files_pdf,
        data={"media_type": MediaType.image.value},
        headers=headers,
    )
    assert res_pdf.status_code == 415

    # Plain text for audio
    files_txt = {"file": ("notes.txt", io.BytesIO(b"hello world"), "text/plain")}
    res_txt = media_client.post(
        f"/api/v1/listings/{listing_id}/media",
        files=files_txt,
        data={"media_type": MediaType.audio.value},
        headers=headers,
    )
    assert res_txt.status_code == 415


def test_media_type_mismatch_rejected(
    media_client: TestClient,
    seller_and_auth,
):
    """Verify uploading an audio MIME type with media_type=image is rejected with 415."""
    _, headers = seller_and_auth
    listing_id = "lst-mismatch"

    files = {"file": ("sound.wav", io.BytesIO(b"audio-bytes"), "audio/wav")}
    res = media_client.post(
        f"/api/v1/listings/{listing_id}/media",
        files=files,
        data={"media_type": MediaType.image.value},
        headers=headers,
    )
    assert res.status_code == 415


def test_extension_mismatch_rejected(
    media_client: TestClient,
    seller_and_auth,
):
    """Verify executable or disallowed extension disguised with valid MIME type is rejected with 415."""
    _, headers = seller_and_auth
    listing_id = "lst-ext-mismatch"

    files = {"file": ("malicious.exe", io.BytesIO(b"binary"), "image/jpeg")}
    res = media_client.post(
        f"/api/v1/listings/{listing_id}/media",
        files=files,
        data={"media_type": MediaType.image.value},
        headers=headers,
    )
    assert res.status_code == 415


def test_oversized_upload_rejected_and_cleaned_up(
    media_client: TestClient,
    isolated_storage: Path,
    seller_and_auth,
    monkeypatch,
):
    """Verify uploads exceeding MAX_MEDIA_UPLOAD_SIZE return 413 and leave no partial file on disk."""
    _, headers = seller_and_auth
    listing_id = "lst-oversized"

    # Set maximum upload size to 256 bytes for test
    monkeypatch.setattr(settings, "MAX_MEDIA_UPLOAD_SIZE", 256)

    large_payload = b"A" * 1024  # 1 KB > 256 bytes
    files = {"file": ("large_image.jpg", io.BytesIO(large_payload), "image/jpeg")}
    data = {"media_type": MediaType.image.value}

    response = media_client.post(f"/api/v1/listings/{listing_id}/media", files=files, data=data, headers=headers)
    assert response.status_code == 413
    assert "maximum allowed upload size" in response.json()["detail"].lower()

    # Verify no partial files exist in the storage directory
    listing_dir = isolated_storage / listing_id
    if listing_dir.exists():
        assert len(list(listing_dir.iterdir())) == 0


def test_empty_file_upload_rejected(
    media_client: TestClient,
    isolated_storage: Path,
    seller_and_auth,
):
    """Verify 0-byte file upload returns 400 Bad Request and leaves no file on disk."""
    _, headers = seller_and_auth
    listing_id = "lst-empty"

    files = {"file": ("empty.jpg", io.BytesIO(b""), "image/jpeg")}
    data = {"media_type": MediaType.image.value}

    response = media_client.post(f"/api/v1/listings/{listing_id}/media", files=files, data=data, headers=headers)
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()

    listing_dir = isolated_storage / listing_id
    if listing_dir.exists():
        assert len(list(listing_dir.iterdir())) == 0


def test_unauthenticated_upload_rejected(
    media_client: TestClient,
):
    """Verify request without Authorization header returns 401 Unauthorized."""
    listing_id = "lst-unauth"
    files = {"file": ("test.jpg", io.BytesIO(b"fake-bytes"), "image/jpeg")}
    data = {"media_type": MediaType.image.value}

    response = media_client.post(f"/api/v1/listings/{listing_id}/media", files=files, data=data)
    assert response.status_code == 401


def test_invalid_token_upload_rejected(
    media_client: TestClient,
):
    """Verify request with invalid Bearer token returns 401 Unauthorized."""
    listing_id = "lst-invalid-token"
    files = {"file": ("test.jpg", io.BytesIO(b"fake-bytes"), "image/jpeg")}
    data = {"media_type": MediaType.image.value}

    response = media_client.post(
        f"/api/v1/listings/{listing_id}/media",
        files=files,
        data=data,
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert response.status_code == 401


def test_media_metadata_persisted_when_listing_exists_in_db(
    media_client: TestClient,
    isolated_storage: Path,
    test_db: Session,
    seller_and_auth,
):
    """Verify that when a Listing row exists in the DB, a Media metadata row is inserted and linked."""
    seller, headers = seller_and_auth
    listing = Listing(
        id=uuid.uuid4(),
        seller_id=seller.id,
        client_item_id="client-mobile-001",
        state=ListingState.queued,
    )
    test_db.add(listing)
    test_db.commit()
    test_db.refresh(listing)

    image_content = b"persisted-image-binary-data"
    files = {"file": ("artisan_item.png", io.BytesIO(image_content), "image/png")}
    data = {"media_type": MediaType.image.value}

    response = media_client.post(f"/api/v1/listings/{listing.id}/media", files=files, data=data, headers=headers)
    assert response.status_code == 200
    res = response.json()
    media_uuid = uuid.UUID(res["id"])

    # Query database to confirm Media record was persisted
    media_record = test_db.query(Media).filter(Media.id == media_uuid).first()
    assert media_record is not None
    assert media_record.listing_id == listing.id
    assert media_record.media_type == MediaType.image
    assert media_record.original_filename == "artisan_item.png"
    assert media_record.storage_path == f"{listing.id}/{media_uuid}.png"
    assert media_record.mime_type == "image/png"
    assert media_record.file_size_bytes == len(image_content)


def test_listing_ownership_enforcement_for_persisted_listing(
    media_client: TestClient,
    isolated_storage: Path,
    test_db: Session,
    seller_and_auth,
):
    """Verify that attempting to upload media to another seller's persisted listing returns 403 Forbidden."""
    seller_a, headers_a = seller_and_auth

    # Create Seller B and an associated Listing
    seller_b = Seller(
        id=uuid.uuid4(),
        firebase_uid="firebase-user-artisan-2",
        phone_number="+919876543211",
        name="Artisan Mohan Lal",
    )
    test_db.add(seller_b)
    test_db.commit()

    listing_b = Listing(
        id=uuid.uuid4(),
        seller_id=seller_b.id,
        client_item_id="client-mobile-b",
        state=ListingState.queued,
    )
    test_db.add(listing_b)
    test_db.commit()

    # Seller A attempts to upload media to Seller B's listing
    files = {"file": ("item.jpg", io.BytesIO(b"bytes"), "image/jpeg")}
    data = {"media_type": MediaType.image.value}

    response = media_client.post(f"/api/v1/listings/{listing_b.id}/media", files=files, data=data, headers=headers_a)
    assert response.status_code == 403
    assert "does not belong" in response.json()["detail"].lower()

    # Confirm no file was left on disk
    listing_dir = isolated_storage / str(listing_b.id)
    if listing_dir.exists():
        assert len(list(listing_dir.iterdir())) == 0


def test_failed_db_persistence_cleans_up_orphaned_file(
    media_client: TestClient,
    isolated_storage: Path,
    test_db: Session,
    seller_and_auth,
):
    """Verify that if database commit fails, the newly created disk file is removed (atomicity)."""
    seller, headers = seller_and_auth
    listing = Listing(
        id=uuid.uuid4(),
        seller_id=seller.id,
        client_item_id="client-atomicity-001",
        state=ListingState.queued,
    )
    test_db.add(listing)
    test_db.commit()

    files = {"file": ("photo.jpg", io.BytesIO(b"atomicity-test-payload"), "image/jpeg")}
    data = {"media_type": MediaType.image.value}

    # Simulate database failure during commit
    with patch.object(Session, "commit", side_effect=RuntimeError("Simulated database write error")):
        response = media_client.post(
            f"/api/v1/listings/{listing.id}/media",
            files=files,
            data=data,
            headers=headers,
        )
        assert response.status_code == 500

    # Verify no file remained on disk
    listing_dir = isolated_storage / str(listing.id)
    if listing_dir.exists():
        assert len(list(listing_dir.iterdir())) == 0


def test_unpersisted_stub_listing_seam_preserved(
    media_client: TestClient,
    isolated_storage: Path,
    seller_and_auth,
):
    """Verify that uploading to a non-UUID or unpersisted stub listing works without database error."""
    _, headers = seller_and_auth
    stub_listing_id = "lst-stub-arbitrary-string-001"

    files = {"file": ("test.jpg", io.BytesIO(b"stub-listing-bytes"), "image/jpeg")}
    data = {"media_type": MediaType.image.value}

    response = media_client.post(
        f"/api/v1/listings/{stub_listing_id}/media",
        files=files,
        data=data,
        headers=headers,
    )
    assert response.status_code == 200
    res = response.json()
    assert res["listing_id"] == stub_listing_id
    assert res["status"] == "uploaded"

    stored_file = isolated_storage / stub_listing_id / f"{res['id']}.jpg"
    assert stored_file.is_file()


def _upload(client: TestClient, listing_id, headers, media_type: MediaType):
    """Upload one media file of the given type to a listing."""
    if media_type is MediaType.image:
        payload = ("craft.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01", "image/jpeg")
    else:
        payload = ("note.wav", b"RIFF....WAVEfmt ....data....", "audio/wav")
    return client.post(
        f"/api/v1/listings/{listing_id}/media",
        files={"file": (payload[0], io.BytesIO(payload[1]), payload[2])},
        data={"media_type": media_type.value},
        headers=headers,
    )


@pytest.fixture(scope="function")
def persisted_listing(test_db: Session, seller_and_auth):
    """A queued listing owned by the authenticated test seller."""
    seller, headers = seller_and_auth
    listing = Listing(
        id=uuid.uuid4(),
        seller_id=seller.id,
        client_item_id=f"capture-{uuid.uuid4()}",
        state=ListingState.queued,
    )
    test_db.add(listing)
    test_db.commit()
    test_db.refresh(listing)
    return listing, headers


def test_pipeline_not_triggered_until_both_media_present(
    media_client: TestClient,
    isolated_storage: Path,
    persisted_listing,
):
    """A photo alone must not start the pipeline: the speech stage needs audio too."""
    listing, headers = persisted_listing

    with patch("app.api.routes.media.process_listing") as mock_process:
        assert _upload(media_client, listing.id, headers, MediaType.image).status_code == 200

    mock_process.assert_not_called()


def test_pipeline_triggered_once_photo_and_voice_note_are_both_uploaded(
    media_client: TestClient,
    isolated_storage: Path,
    persisted_listing,
):
    """The upload completing the photo/voice-note pair schedules the pipeline."""
    listing, headers = persisted_listing

    with patch("app.api.routes.media.process_listing") as mock_process:
        assert _upload(media_client, listing.id, headers, MediaType.image).status_code == 200
        assert _upload(media_client, listing.id, headers, MediaType.audio).status_code == 200

    mock_process.assert_called_once_with(listing_id=listing.id, seller_id=listing.seller_id)


def test_pipeline_not_retriggered_for_a_listing_already_processing(
    media_client: TestClient,
    isolated_storage: Path,
    test_db: Session,
    persisted_listing,
):
    """Extra uploads on an in-flight listing must not queue a second pipeline run."""
    listing, headers = persisted_listing

    with patch("app.api.routes.media.process_listing") as mock_process:
        assert _upload(media_client, listing.id, headers, MediaType.image).status_code == 200
        assert _upload(media_client, listing.id, headers, MediaType.audio).status_code == 200
        mock_process.assert_called_once()
        mock_process.reset_mock()

        listing.state = ListingState.processing
        test_db.commit()

        assert _upload(media_client, listing.id, headers, MediaType.image).status_code == 200

    mock_process.assert_not_called()


def test_pipeline_not_triggered_for_unpersisted_stub_listing(
    media_client: TestClient,
    isolated_storage: Path,
    seller_and_auth,
):
    """The stub-listing seam still short-circuits before any pipeline work."""
    seller, headers = seller_and_auth

    with patch("app.api.routes.media.process_listing") as mock_process:
        assert _upload(media_client, "lst-stub-909", headers, MediaType.image).status_code == 200
        assert _upload(media_client, "lst-stub-909", headers, MediaType.audio).status_code == 200

    mock_process.assert_not_called()


def _listing_with_photo(test_db: Session, seller, isolated_storage: Path):
    """A persisted listing whose single photo is on disk as the artisan sent it."""
    listing = Listing(
        id=uuid.uuid4(),
        seller_id=seller.id,
        client_item_id="client-mobile-vision",
        state=ListingState.ready,
    )
    test_db.add(listing)
    test_db.commit()

    media_id = uuid.uuid4()
    raw_rel = f"{listing.id}/{media_id}.jpg"
    raw_path = isolated_storage / raw_rel
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(b"raw-camera-frame")

    media = Media(
        id=media_id,
        listing_id=listing.id,
        media_type=MediaType.image,
        original_filename="artisan_item.jpg",
        storage_path=raw_rel,
        mime_type="image/jpeg",
        file_size_bytes=raw_path.stat().st_size,
    )
    test_db.add(media)
    test_db.commit()
    return listing, media


def _write_composite(test_db: Session, media: Media, isolated_storage: Path) -> Path:
    """Stand in for the Vision Station writing a studio image for `media`."""
    clean_rel = f"{media.listing_id}/vision/{media.id}_clean.jpg"
    clean_path = isolated_storage / clean_rel
    clean_path.parent.mkdir(parents=True, exist_ok=True)
    clean_path.write_bytes(b"studio-composite")
    media.processed_path = clean_rel
    test_db.add(media)
    test_db.commit()
    return clean_path


def test_media_endpoint_serves_the_vision_composite_once_one_exists(
    media_client: TestClient,
    isolated_storage: Path,
    test_db: Session,
    seller_and_auth,
):
    """The polished image has to be what this URL returns, or it never reaches the listing."""
    seller, headers = seller_and_auth
    listing, media = _listing_with_photo(test_db, seller, isolated_storage)

    before = media_client.get(f"/api/v1/listings/{listing.id}/media/{media.id}", headers=headers)
    assert before.status_code == 200
    assert before.content == b"raw-camera-frame"

    _write_composite(test_db, media, isolated_storage)

    after = media_client.get(f"/api/v1/listings/{listing.id}/media/{media.id}", headers=headers)
    assert after.status_code == 200
    assert after.content == b"studio-composite"
    # The composite is written as JPEG whatever the phone uploaded.
    assert after.headers["content-type"] == "image/jpeg"


def test_media_endpoint_falls_back_to_the_upload_when_the_composite_is_gone(
    media_client: TestClient,
    isolated_storage: Path,
    test_db: Session,
    seller_and_auth,
):
    """A missing studio image must not cost the artisan their photo."""
    seller, headers = seller_and_auth
    listing, media = _listing_with_photo(test_db, seller, isolated_storage)
    clean_path = _write_composite(test_db, media, isolated_storage)
    clean_path.unlink()

    response = media_client.get(f"/api/v1/listings/{listing.id}/media/{media.id}", headers=headers)
    assert response.status_code == 200
    assert response.content == b"raw-camera-frame"


def test_listing_image_url_changes_when_the_composite_appears(
    isolated_storage: Path,
    test_db: Session,
    seller_and_auth,
):
    """The app caches by URL, so the same URL would keep showing the camera frame."""
    from app.services.listing_view import listing_image_urls

    seller, _ = seller_and_auth
    listing, media = _listing_with_photo(test_db, seller, isolated_storage)
    test_db.refresh(listing)

    raw_urls = listing_image_urls(listing)
    assert raw_urls == [f"/api/v1/listings/{listing.id}/media/{media.id}"]

    _write_composite(test_db, media, isolated_storage)
    test_db.refresh(listing)

    processed_urls = listing_image_urls(listing)
    assert processed_urls != raw_urls
    assert processed_urls[0].startswith(raw_urls[0] + "?v=")


def test_typed_description_waits_for_every_photo_before_processing(
    media_client: TestClient,
    isolated_storage: Path,
    test_db: Session,
    persisted_listing,
):
    """The run must see the whole set, or the later photos are never composited.

    A typed description already satisfies "an account of the piece", so without
    the declared count the first photo started the run and the artisan's other
    photos landed after it had read its media - published as raw camera frames
    while the first one came back as a studio image.
    """
    listing, headers = persisted_listing
    listing.typed_description = "Bronze bangles, five days of work."
    listing.expected_photo_count = 3
    test_db.add(listing)
    test_db.commit()

    with patch("app.api.routes.media.process_listing") as mock_process:
        assert _upload(media_client, listing.id, headers, MediaType.image).status_code == 200
        assert _upload(media_client, listing.id, headers, MediaType.image).status_code == 200
        mock_process.assert_not_called()

        assert _upload(media_client, listing.id, headers, MediaType.image).status_code == 200

    mock_process.assert_called_once_with(listing_id=listing.id, seller_id=listing.seller_id)


def test_voice_note_still_completes_the_set_whatever_the_declared_count(
    media_client: TestClient,
    isolated_storage: Path,
    test_db: Session,
    persisted_listing,
):
    """The recording is uploaded last, so it is itself proof the capture is done."""
    listing, headers = persisted_listing
    listing.expected_photo_count = 3
    test_db.add(listing)
    test_db.commit()

    with patch("app.api.routes.media.process_listing") as mock_process:
        assert _upload(media_client, listing.id, headers, MediaType.image).status_code == 200
        mock_process.assert_not_called()
        assert _upload(media_client, listing.id, headers, MediaType.audio).status_code == 200

    mock_process.assert_called_once_with(listing_id=listing.id, seller_id=listing.seller_id)
