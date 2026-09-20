"""Comprehensive tests for Firebase authentication, seller identity resolution, application JWTs, and profile endpoints."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Generator
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.firebase import (
    FirebaseAuthenticationError,
    FirebasePhoneMissingError,
    FirebaseTokenExpiredError,
    FirebaseTokenInvalidError,
    FirebaseTokenMissingError,
    FirebaseTokenRevokedError,
    verify_firebase_id_token,
)
from app.core.phone import normalize_phone_number
from app.core.security import create_access_token, decode_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.seller import Seller


@pytest.fixture(scope="function")
def test_engine():
    """Create an isolated thread-safe in-memory SQLite database engine for testing."""
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
def test_db(test_engine):
    """Provide a session bound to the in-memory test database."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="function")
def auth_client(test_engine):
    """FastAPI TestClient configured with thread-safe test database session override."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_phone_normalization_valid_international():
    """Verify various valid international phone numbers are normalized to E.164-like canonical form."""
    assert normalize_phone_number("+91 98765 43210") == "+919876543210"
    assert normalize_phone_number("+1 (415) 555-2671") == "+14155552671"
    assert normalize_phone_number("+44 20 7946 0991") == "+442079460991"
    assert normalize_phone_number("  +81-3-1234-5678  ") == "+81312345678"


def test_phone_normalization_invalid_inputs():
    """Verify malformed or invalid phone numbers raise ValueError."""
    # Missing country code
    with pytest.raises(ValueError, match="starting with '\\+'"):
        normalize_phone_number("9876543210")

    # Empty or whitespace
    with pytest.raises(ValueError):
        normalize_phone_number("")

    # Contains alphabetic characters
    with pytest.raises(ValueError, match="non-numeric"):
        normalize_phone_number("+9198765ABCD0")

    # Too short
    with pytest.raises(ValueError, match="outside valid range"):
        normalize_phone_number("+1234")

    # Too long (over 15 digits)
    with pytest.raises(ValueError, match="outside valid range"):
        normalize_phone_number("+1234567890123456789")


def test_verify_firebase_token_missing():
    """Verify missing or whitespace token raises FirebaseTokenMissingError."""
    with pytest.raises(FirebaseTokenMissingError):
        verify_firebase_id_token("")

    with pytest.raises(FirebaseTokenMissingError):
        verify_firebase_id_token("   ")


@patch("app.core.firebase.fb_auth.verify_id_token")
@patch("app.core.firebase.initialize_firebase")
def test_verify_firebase_token_valid(mock_init, mock_verify):
    """Verify successful decoding and extraction of UID and phone claim."""
    mock_verify.return_value = {
        "uid": "fb-artisan-100",
        "phone_number": "+91 98765 43210",
        "iss": "https://securetoken.google.com/test-project",
    }
    result = verify_firebase_id_token("valid-mock-token")
    assert result["uid"] == "fb-artisan-100"
    assert result["phone_number"] == "+919876543210"
    assert "claims" in result


@patch("app.core.firebase.fb_auth.verify_id_token")
@patch("app.core.firebase.initialize_firebase")
def test_verify_firebase_token_missing_phone(mock_init, mock_verify):
    """Verify token missing phone claim raises FirebasePhoneMissingError."""
    mock_verify.return_value = {
        "uid": "fb-user-no-phone",
        "email": "user@example.com",
    }
    with pytest.raises(FirebasePhoneMissingError, match="verified phone number"):
        verify_firebase_id_token("token-without-phone")


@patch("app.core.firebase.fb_auth.verify_id_token")
@patch("app.core.firebase.initialize_firebase")
def test_verify_firebase_token_expired(mock_init, mock_verify):
    """Verify expired token raises FirebaseTokenExpiredError."""
    from firebase_admin import auth as fb_auth
    mock_verify.side_effect = fb_auth.ExpiredIdTokenError("Token expired", None)
    with pytest.raises(FirebaseTokenExpiredError):
        verify_firebase_id_token("expired-token")


@patch("app.core.firebase.fb_auth.verify_id_token")
@patch("app.core.firebase.initialize_firebase")
def test_verify_firebase_token_invalid(mock_init, mock_verify):
    """Verify cryptographically invalid token raises FirebaseTokenInvalidError."""
    from firebase_admin import auth as fb_auth
    mock_verify.side_effect = fb_auth.InvalidIdTokenError("Invalid token")
    with pytest.raises(FirebaseTokenInvalidError):
        verify_firebase_id_token("invalid-token")


@patch("app.services.auth.verify_firebase_id_token")
def test_firebase_auth_first_login_creates_seller(mock_verify, auth_client: TestClient, test_db: Session):
    """Verify first-time phone auth creates a new seller entity and issues an application JWT."""
    mock_verify.return_value = {
        "uid": "firebase-uid-new",
        "phone_number": "+919876500001",
        "claims": {"uid": "firebase-uid-new", "phone_number": "+919876500001"},
    }

    response = auth_client.post("/api/v1/auth/firebase", json={"id_token": "valid-token-1"})
    assert response.status_code == 200
    data = response.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"
    seller_data = data["seller"]
    assert "id" in seller_data
    assert seller_data["phone_number"] == "+919876500001"
    assert seller_data["name"] == ""
    assert seller_data["cluster"] is None

    # Verify database persistence
    seller_in_db = test_db.query(Seller).filter(Seller.firebase_uid == "firebase-uid-new").first()
    assert seller_in_db is not None
    assert seller_in_db.phone_number == "+919876500001"

    # Decode and verify issued application JWT
    payload = decode_access_token(data["access_token"])
    assert payload["sub"] == str(seller_in_db.id)


@patch("app.services.auth.verify_firebase_id_token")
def test_firebase_auth_existing_uid_returns_same_seller(mock_verify, auth_client: TestClient, test_db: Session):
    """Verify subsequent login with existing Firebase UID returns the same seller without duplication."""
    mock_verify.return_value = {
        "uid": "firebase-uid-repeat",
        "phone_number": "+919876500002",
        "claims": {},
    }

    # First login
    res1 = auth_client.post("/api/v1/auth/firebase", json={"id_token": "token-1"})
    assert res1.status_code == 200
    seller_id_1 = res1.json()["seller"]["id"]

    # Second login
    res2 = auth_client.post("/api/v1/auth/firebase", json={"id_token": "token-2"})
    assert res2.status_code == 200
    seller_id_2 = res2.json()["seller"]["id"]

    assert seller_id_1 == seller_id_2
    assert test_db.query(Seller).filter(Seller.firebase_uid == "firebase-uid-repeat").count() == 1


@patch("app.services.auth.verify_firebase_id_token")
def test_firebase_auth_existing_phone_associates_uid(mock_verify, auth_client: TestClient, test_db: Session):
    """Verify an existing seller with matching phone number but no UID has the Firebase UID linked safely."""
    # Seed seller with phone but no firebase_uid
    existing_seller = Seller(
        name="Artisan Shyam",
        language="hi",
        phone_number="+919876500003",
        firebase_uid=None,
    )
    test_db.add(existing_seller)
    test_db.commit()
    test_db.refresh(existing_seller)

    mock_verify.return_value = {
        "uid": "firebase-uid-newly-linked",
        "phone_number": "+919876500003",
        "claims": {},
    }

    response = auth_client.post("/api/v1/auth/firebase", json={"id_token": "token-3"})
    assert response.status_code == 200
    assert response.json()["seller"]["id"] == str(existing_seller.id)
    assert response.json()["seller"]["name"] == "Artisan Shyam"

    test_db.refresh(existing_seller)
    assert existing_seller.firebase_uid == "firebase-uid-newly-linked"


@patch("app.services.auth.verify_firebase_id_token")
def test_identity_conflict_uid_with_differing_phone(mock_verify, auth_client: TestClient, test_db: Session):
    """Case A: UID belongs to seller A, but token phone differs from stored phone -> 401."""
    seller = Seller(
        firebase_uid="uid-seller-a",
        phone_number="+911111111111",
        name="Seller A",
    )
    test_db.add(seller)
    test_db.commit()

    mock_verify.return_value = {
        "uid": "uid-seller-a",
        "phone_number": "+912222222222",  # Different phone
        "claims": {},
    }

    response = auth_client.post("/api/v1/auth/firebase", json={"id_token": "token-conflict"})
    assert response.status_code == 401
    assert "Identity conflict" in response.json()["detail"]


@patch("app.services.auth.verify_firebase_id_token")
def test_identity_conflict_phone_belongs_to_another_firebase_user(mock_verify, auth_client: TestClient, test_db: Session):
    """Case B: Phone belongs to seller B with another UID -> 401."""
    seller_b = Seller(
        firebase_uid="uid-seller-b",
        phone_number="+913333333333",
        name="Seller B",
    )
    test_db.add(seller_b)
    test_db.commit()

    mock_verify.return_value = {
        "uid": "uid-new-attacker",  # Different UID claiming seller B's phone
        "phone_number": "+913333333333",
        "claims": {},
    }

    response = auth_client.post("/api/v1/auth/firebase", json={"id_token": "token-hijack"})
    assert response.status_code == 401
    assert "Identity conflict" in response.json()["detail"]


@patch("app.services.auth.verify_firebase_id_token")
def test_firebase_auth_error_scenarios(mock_verify, auth_client: TestClient):
    """Verify all Firebase error scenarios return 401 Unauthorized."""
    # 1. Expired token
    mock_verify.side_effect = FirebaseTokenExpiredError("Token expired")
    res1 = auth_client.post("/api/v1/auth/firebase", json={"id_token": "expired"})
    assert res1.status_code == 401

    # 2. Invalid token
    mock_verify.side_effect = FirebaseTokenInvalidError("Token signature invalid")
    res2 = auth_client.post("/api/v1/auth/firebase", json={"id_token": "invalid"})
    assert res2.status_code == 401

    # 3. Missing phone claim
    mock_verify.side_effect = FirebasePhoneMissingError("Verified phone required")
    res3 = auth_client.post("/api/v1/auth/firebase", json={"id_token": "no-phone"})
    assert res3.status_code == 401

    # 4. Empty token payload
    res4 = auth_client.post("/api/v1/auth/firebase", json={})
    assert res4.status_code == 422


def test_jwt_valid_seller_resolution(auth_client: TestClient, test_db: Session):
    """Verify valid application JWT successfully authenticates protected GET /api/v1/seller."""
    seller = Seller(name="Artisan Radha Devi", language="hi", phone_number="+919876543210")
    test_db.add(seller)
    test_db.commit()
    test_db.refresh(seller)

    token = create_access_token(seller.id)
    response = auth_client.get("/api/v1/seller", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(seller.id)
    assert data["name"] == "Artisan Radha Devi"
    assert data["phone_number"] == "+919876543210"


def test_jwt_missing_authorization_header(auth_client: TestClient):
    """Verify request without Authorization header returns 401."""
    response = auth_client.get("/api/v1/seller")
    assert response.status_code == 401


def test_jwt_invalid_signature(auth_client: TestClient, test_db: Session):
    """Verify token signed with wrong secret key returns 401."""
    seller = Seller(name="Test", language="hi")
    test_db.add(seller)
    test_db.commit()

    fake_token = jwt.encode(
        {"sub": str(seller.id), "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())},
        "wrong-secret-key-that-is-at-least-32-bytes-long",
        algorithm="HS256",
    )
    response = auth_client.get("/api/v1/seller", headers={"Authorization": f"Bearer {fake_token}"})
    assert response.status_code == 401


def test_jwt_expired_token(auth_client: TestClient, test_db: Session):
    """Verify expired token returns 401."""
    seller = Seller(name="Test", language="hi")
    test_db.add(seller)
    test_db.commit()

    expired_token = create_access_token(seller.id, expires_delta=timedelta(minutes=-10))
    response = auth_client.get("/api/v1/seller", headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401


def test_jwt_nonexistent_seller(auth_client: TestClient):
    """Verify token identifying a deleted/nonexistent seller ID returns 401."""
    random_id = uuid.uuid4()
    token = create_access_token(random_id)
    response = auth_client.get("/api/v1/seller", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Seller not found"


def test_jwt_malformed_token(auth_client: TestClient):
    """Verify arbitrary malformed token string returns 401."""
    response = auth_client.get("/api/v1/seller", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert response.status_code == 401


def test_seller_isolation(auth_client: TestClient, test_db: Session):
    """Verify Seller A cannot retrieve Seller B's profile."""
    seller_a = Seller(name="Artisan A", language="hi", phone_number="+911111111111")
    seller_b = Seller(name="Artisan B", language="en", phone_number="+912222222222")
    test_db.add_all([seller_a, seller_b])
    test_db.commit()

    token_a = create_access_token(seller_a.id)
    token_b = create_access_token(seller_b.id)

    res_a = auth_client.get("/api/v1/seller", headers={"Authorization": f"Bearer {token_a}"})
    res_b = auth_client.get("/api/v1/seller", headers={"Authorization": f"Bearer {token_b}"})

    assert res_a.json()["id"] == str(seller_a.id)
    assert res_a.json()["name"] == "Artisan A"

    assert res_b.json()["id"] == str(seller_b.id)
    assert res_b.json()["name"] == "Artisan B"


def test_seller_profile_update_success(auth_client: TestClient, test_db: Session):
    """Verify authenticated PUT /api/v1/seller updates allowed profile fields."""
    seller = Seller(name="", language="hi", cluster=None, phone_number="+919876543210")
    test_db.add(seller)
    test_db.commit()

    token = create_access_token(seller.id)
    update_payload = {
        "name": "Artisan Meera Bai",
        "language": "hi",
        "cluster": "Jaipur Craft Cluster",
    }
    response = auth_client.put(
        "/api/v1/seller",
        json=update_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Artisan Meera Bai"
    assert data["cluster"] == "Jaipur Craft Cluster"
    assert data["language"] == "hi"

    # Verify database update
    test_db.refresh(seller)
    assert seller.name == "Artisan Meera Bai"
    assert seller.cluster == "Jaipur Craft Cluster"


def test_seller_profile_update_unauthenticated(auth_client: TestClient):
    """Verify unauthenticated PUT /api/v1/seller returns 401."""
    response = auth_client.put("/api/v1/seller", json={"name": "New Name"})
    assert response.status_code == 401


def test_seller_profile_update_immutable_fields_rejected(auth_client: TestClient, test_db: Session):
    """Verify attempting to modify immutable fields (id, firebase_uid, phone_number) is rejected."""
    seller = Seller(
        name="Artisan Sita",
        language="hi",
        firebase_uid="original-uid",
        phone_number="+919999999999",
    )
    test_db.add(seller)
    test_db.commit()

    token = create_access_token(seller.id)

    # Extra fields are forbidden by SellerUpdateRequest model config
    tamper_payload = {
        "name": "Updated Sita",
        "firebase_uid": "tampered-uid",
        "phone_number": "+910000000000",
    }
    response = auth_client.put(
        "/api/v1/seller",
        json=tamper_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422

    # Verify original identity values remained intact
    test_db.refresh(seller)
    assert seller.firebase_uid == "original-uid"
    assert seller.phone_number == "+919999999999"
