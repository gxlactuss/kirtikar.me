"""Each demo run is copied to storage that outlives the container."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.listing import Listing
from app.models.listing_result import ListingResult
from app.models.media import Media
from app.models.seller import Seller
from app.schemas.enums import ListingState, MediaType
from app.services.run_archive import write_run


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def db(engine) -> Generator[Session, None, None]:
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def archive(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "runs"
    monkeypatch.setattr(settings, "RUN_ARCHIVE_DIR", str(path))
    monkeypatch.setattr(settings, "MEDIA_STORAGE_DIR", str(tmp_path / "media"))
    return path


@pytest.fixture
def seller(db: Session) -> Seller:
    seller = Seller(id=uuid.uuid4(), firebase_uid="fb-archive", phone_number="+919800000000")
    db.add(seller)
    db.commit()
    return seller


def _only_run(archive: Path) -> Path:
    runs = list(archive.iterdir())
    assert len(runs) == 1
    return runs[0]


def test_create_records_the_visitor(engine, archive: Path, seller: Seller):
    def override_get_db():
        session = sessionmaker(bind=engine)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).post(
            "/api/v1/listings",
            json={"client_item_id": "c-1", "visitor_name": "  Asha  "},
            headers={
                "Authorization": f"Bearer {create_access_token(seller_id=seller.id)}",
                "X-Forwarded-For": "203.0.113.7, 10.0.0.1",
                "User-Agent": "TestPhone/1.0",
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    run = _only_run(archive)
    assert run.name.endswith(response.json()["id"])
    visitor = json.loads((run / "visitor.json").read_text())
    assert visitor["name"] == "Asha"
    assert visitor["ip"] == "203.0.113.7"
    assert visitor["user_agent"] == "TestPhone/1.0"


def test_a_run_keeps_the_product_and_its_media(db: Session, archive: Path, seller: Seller):
    media_root = Path(settings.MEDIA_STORAGE_DIR)
    (media_root / "l").mkdir(parents=True)
    (media_root / "l" / "photo.jpg").write_bytes(b"raw")
    (media_root / "l" / "photo_clean.jpg").write_bytes(b"clean")
    (media_root / "l" / "voice.wav").write_bytes(b"wav")

    listing = Listing(
        id=uuid.uuid4(),
        seller_id=seller.id,
        client_item_id="c-2",
        state=ListingState.ready,
        # 06:22 UTC is 11:52 IST, which is what the folder should say.
        created_at=datetime(2026, 10, 7, 6, 22, 42, tzinfo=timezone.utc),
    )
    db.add(listing)
    db.add(ListingResult(listing_id=listing.id, title="Brass lamp", transcript="yeh diya hai"))
    db.add_all(
        [
            Media(
                id=uuid.uuid4(), listing_id=listing.id, media_type=MediaType.image,
                storage_path="l/photo.jpg", processed_path="l/photo_clean.jpg",
            ),
            Media(
                id=uuid.uuid4(), listing_id=listing.id, media_type=MediaType.audio,
                storage_path="l/voice.wav",
            ),
        ]
    )
    db.commit()
    db.refresh(listing)

    write_run(listing)
    write_run(listing)  # a later save rewrites in place rather than duplicating

    run = _only_run(archive)
    assert run.name == f"2026-10-07_115242_{listing.id}"
    saved = json.loads((run / "run.json").read_text())
    assert saved["listing"]["title"] == "Brass lamp"
    assert saved["transcript"] == "yeh diya hai"
    assert sorted(p.name for p in (run / "media").iterdir()) == [
        "photo.jpg", "photo_clean.jpg", "voice.wav",
    ]


def test_nothing_is_kept_without_an_archive_dir(db: Session, seller: Seller, monkeypatch):
    monkeypatch.setattr(settings, "RUN_ARCHIVE_DIR", None)
    listing = Listing(seller_id=seller.id, client_item_id="c-3", state=ListingState.queued)
    db.add(listing)
    db.commit()
    write_run(listing)  # must not raise
