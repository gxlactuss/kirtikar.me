"""Firebase Admin SDK integration and ID-token verification service."""
import json
import os
from typing import Any, Dict, Optional

import logging

import firebase_admin
from firebase_admin import auth as fb_auth, credentials

from app.core.config import settings
from app.core.phone import normalize_phone_number

logger = logging.getLogger("app.core.firebase")


class FirebaseAuthenticationError(Exception):
    """Base exception for Firebase authentication failures."""
    pass


class FirebaseTokenMissingError(FirebaseAuthenticationError):
    """Raised when the Firebase ID token is absent or empty."""
    pass


class FirebaseTokenInvalidError(FirebaseAuthenticationError):
    """Raised when the Firebase ID token is structurally invalid or forged."""
    pass


class FirebaseTokenExpiredError(FirebaseAuthenticationError):
    """Raised when the Firebase ID token has expired."""
    pass


class FirebaseTokenRevokedError(FirebaseAuthenticationError):
    """Raised when the Firebase ID token has been revoked."""
    pass


class FirebasePhoneMissingError(FirebaseAuthenticationError):
    """Raised when the verified Firebase token lacks an authoritative phone claim."""
    pass


_firebase_app: Optional[firebase_admin.App] = None

# True when a service account was supplied. Revocation checking calls the
# Firebase Auth API, which needs privileged credentials; signature, audience
# and expiry checks need only the project id and Google's public certificates.
_has_service_account: bool = False


class _PublicCertsOnlyCredential(credentials.Base):
    """A credential that authenticates nothing.

    Verifying an ID token needs only Google's public signing certificates, which
    are served from a public endpoint. The Admin SDK still asks its app for a
    credential when it builds the auth client, though, and the default lookup
    fails on a machine with no service account and no gcloud login. This
    satisfies that construction without pretending to hold any authority.
    """

    def get_credential(self) -> Any:
        from google.auth.credentials import AnonymousCredentials

        return AnonymousCredentials()


def has_privileged_credentials() -> bool:
    """Whether the Admin SDK can call the Firebase Auth API, not just verify."""
    initialize_firebase()
    return _has_service_account


def initialize_firebase() -> firebase_admin.App:
    """Initialize the Firebase Admin SDK singleton exactly once using application configuration."""
    global _firebase_app, _has_service_account
    if _firebase_app is not None:
        return _firebase_app

    # Check if default app was already initialized elsewhere
    if firebase_admin._apps:
        _firebase_app = firebase_admin.get_app()
        return _firebase_app

    # Option 1: Inline JSON string in environment variable
    if settings.FIREBASE_SERVICE_ACCOUNT_JSON:
        try:
            cert_dict = json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON)
            cred = credentials.Certificate(cert_dict)
            _firebase_app = firebase_admin.initialize_app(cred)
            _has_service_account = True
            return _firebase_app
        except Exception as err:
            raise RuntimeError(f"Failed to parse FIREBASE_SERVICE_ACCOUNT_JSON: {err}") from err

    # Option 2: Path to service account file
    if settings.FIREBASE_SERVICE_ACCOUNT_PATH:
        if not os.path.isfile(settings.FIREBASE_SERVICE_ACCOUNT_PATH):
            raise RuntimeError(
                f"Configured FIREBASE_SERVICE_ACCOUNT_PATH does not exist: {settings.FIREBASE_SERVICE_ACCOUNT_PATH}"
            )
        cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_PATH)
        _firebase_app = firebase_admin.initialize_app(cred)
        _has_service_account = True
        return _firebase_app

    # Option 3: a project id on its own. An ID token is a signed JWT, so the
    # signature can be checked against Google's public certificates and the
    # audience against the project id, with no secret involved. That is enough
    # to authenticate a caller; it is not enough to administer users, so
    # revocation checking is skipped while running this way.
    if settings.FIREBASE_PROJECT_ID:
        _firebase_app = firebase_admin.initialize_app(
            _PublicCertsOnlyCredential(),
            options={"projectId": settings.FIREBASE_PROJECT_ID},
        )
        _has_service_account = False
        return _firebase_app

    # Otherwise fall back to ambient application default credentials.
    try:
        _firebase_app = firebase_admin.initialize_app()
        _has_service_account = True
        return _firebase_app
    except Exception as err:
        raise RuntimeError(
            "Firebase Admin credentials are not configured. Set "
            "FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_SERVICE_ACCOUNT_PATH, or "
            "FIREBASE_PROJECT_ID."
        ) from err


def verify_firebase_id_token(id_token: str) -> Dict[str, Any]:
    """Verify a Firebase ID token and extract verified identity claims (UID and phone).

    Returns:
        Dict with "uid", "phone_number" (normalized), and "claims".

    Raises:
        FirebaseTokenMissingError: Token is empty or missing.
        FirebaseTokenExpiredError: Token is expired.
        FirebaseTokenRevokedError: Token has been revoked.
        FirebaseTokenInvalidError: Token failed cryptographic signature verification.
        FirebasePhoneMissingError: Token lacks an authoritative phone number claim.
        FirebaseAuthenticationError: General authentication failure.
    """
    if not id_token or not isinstance(id_token, str) or not id_token.strip():
        raise FirebaseTokenMissingError("Firebase ID token must be provided.")

    token = id_token.strip()

    # Ensure Firebase Admin SDK is initialized before verification
    initialize_firebase()

    # Revocation lookups need privileged credentials. Without them the token is
    # still fully verified - signature, audience and expiry - but a token
    # revoked before its expiry would keep working, so it is only skipped when
    # there is no service account to ask with.
    check_revoked = _has_service_account
    if not check_revoked:
        logger.warning(
            "Verifying Firebase ID tokens without a service account: signature, "
            "audience and expiry are checked, revocation is not."
        )

    try:
        decoded_token = fb_auth.verify_id_token(token, check_revoked=check_revoked)
    except fb_auth.ExpiredIdTokenError as err:
        raise FirebaseTokenExpiredError("Firebase ID token has expired.") from err
    except fb_auth.RevokedIdTokenError as err:
        raise FirebaseTokenRevokedError("Firebase ID token has been revoked.") from err
    except (fb_auth.InvalidIdTokenError, ValueError) as err:
        raise FirebaseTokenInvalidError("Invalid Firebase ID token.") from err
    except Exception as err:
        raise FirebaseAuthenticationError(f"Firebase token verification failed: {err}") from err

    uid = decoded_token.get("uid") or decoded_token.get("sub")
    if not uid:
        raise FirebaseTokenInvalidError("Firebase token payload does not contain a valid user identifier (uid).")

    # Authoritative verified phone extraction
    phone_number = decoded_token.get("phone_number")
    if not phone_number:
        identities = decoded_token.get("firebase", {}).get("identities", {})
        phones = identities.get("phone", [])
        if phones:
            phone_number = phones[0]

    if not phone_number:
        raise FirebasePhoneMissingError(
            "Firebase user account does not contain a verified phone number. "
            "Phone-verified authentication is required."
        )

    try:
        normalized_phone = normalize_phone_number(phone_number)
    except ValueError as err:
        raise FirebasePhoneMissingError(f"Verified phone number is malformed: {err}") from err

    return {
        "uid": uid,
        "phone_number": normalized_phone,
        "claims": decoded_token,
    }
