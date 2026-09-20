"""How an ID token is verified, with and without a service account.

An ID token is a signed JWT, so its signature can be checked against Google's
public certificates and its audience against the project id, with no secret
involved. Revocation checking is the one part that calls the Firebase Auth API
and needs privileged credentials, so it is asked for only when it can be.
"""
import pytest

import app.core.firebase as firebase
from app.core.config import settings


@pytest.fixture(autouse=True)
def reset_singleton(monkeypatch):
    """The Admin SDK app is a module singleton; each test gets a clean one."""
    monkeypatch.setattr(firebase, "_firebase_app", None)
    monkeypatch.setattr(firebase, "_has_service_account", False)
    yield


def _stub_initialize(monkeypatch, project_id="sih090"):
    """Stand in for firebase_admin.initialize_app, recording its options."""
    seen = {}

    class _App:
        def __init__(self, options=None, credential=None):
            self.project_id = (options or {}).get("projectId", project_id)

    def _initialize_app(credential=None, options=None):
        seen["credential"] = credential
        seen["options"] = options
        return _App(options=options, credential=credential)

    monkeypatch.setattr(firebase.firebase_admin, "initialize_app", _initialize_app)
    monkeypatch.setattr(firebase.firebase_admin, "_apps", {})
    return seen


def test_a_project_id_alone_is_enough_to_initialise(monkeypatch):
    """No secret on the machine must not stop the API from verifying callers."""
    seen = _stub_initialize(monkeypatch)
    monkeypatch.setattr(settings, "FIREBASE_SERVICE_ACCOUNT_JSON", None)
    monkeypatch.setattr(settings, "FIREBASE_SERVICE_ACCOUNT_PATH", None)
    monkeypatch.setattr(settings, "FIREBASE_PROJECT_ID", "sih090")

    app = firebase.initialize_firebase()

    assert app.project_id == "sih090"
    assert seen["options"] == {"projectId": "sih090"}
    # A credential object is still required to build the auth client, but it
    # carries no authority: verification needs only Google's public certs.
    assert isinstance(seen["credential"], firebase._PublicCertsOnlyCredential)


def test_project_id_mode_reports_no_privileged_credentials(monkeypatch):
    _stub_initialize(monkeypatch)
    monkeypatch.setattr(settings, "FIREBASE_SERVICE_ACCOUNT_JSON", None)
    monkeypatch.setattr(settings, "FIREBASE_SERVICE_ACCOUNT_PATH", None)
    monkeypatch.setattr(settings, "FIREBASE_PROJECT_ID", "sih090")

    assert firebase.has_privileged_credentials() is False


def test_revocation_is_not_asked_for_without_a_service_account(monkeypatch):
    """Asking would fail, so the token is verified without that one check."""
    _stub_initialize(monkeypatch)
    monkeypatch.setattr(settings, "FIREBASE_SERVICE_ACCOUNT_JSON", None)
    monkeypatch.setattr(settings, "FIREBASE_SERVICE_ACCOUNT_PATH", None)
    monkeypatch.setattr(settings, "FIREBASE_PROJECT_ID", "sih090")

    asked = {}

    def _verify(token, check_revoked=False):
        asked["check_revoked"] = check_revoked
        return {"uid": "abc", "phone_number": "+919812345678"}

    monkeypatch.setattr(firebase.fb_auth, "verify_id_token", _verify)

    claims = firebase.verify_firebase_id_token("a.b.c")

    assert asked["check_revoked"] is False
    assert claims["uid"] == "abc"


def test_revocation_is_asked_for_once_a_service_account_exists(monkeypatch, tmp_path):
    """The same code upgrades to full verification the moment a key is set."""
    cert = tmp_path / "service-account.json"
    cert.write_text("{}")

    monkeypatch.setattr(settings, "FIREBASE_SERVICE_ACCOUNT_JSON", None)
    monkeypatch.setattr(settings, "FIREBASE_SERVICE_ACCOUNT_PATH", str(cert))
    monkeypatch.setattr(settings, "FIREBASE_PROJECT_ID", "sih090")

    class _App:
        project_id = "sih090"

    monkeypatch.setattr(firebase.firebase_admin, "_apps", {})
    monkeypatch.setattr(
        firebase.firebase_admin, "initialize_app", lambda *a, **k: _App()
    )
    monkeypatch.setattr(
        firebase.credentials, "Certificate", lambda path: object()
    )

    asked = {}

    def _verify(token, check_revoked=False):
        asked["check_revoked"] = check_revoked
        return {"uid": "abc", "phone_number": "+919812345678"}

    monkeypatch.setattr(firebase.fb_auth, "verify_id_token", _verify)

    firebase.verify_firebase_id_token("a.b.c")

    assert asked["check_revoked"] is True
    assert firebase.has_privileged_credentials() is True


def test_a_token_with_no_phone_is_still_refused(monkeypatch):
    """Phone-verified sign-in is the whole basis of a seller's identity."""
    _stub_initialize(monkeypatch)
    monkeypatch.setattr(settings, "FIREBASE_SERVICE_ACCOUNT_JSON", None)
    monkeypatch.setattr(settings, "FIREBASE_SERVICE_ACCOUNT_PATH", None)
    monkeypatch.setattr(settings, "FIREBASE_PROJECT_ID", "sih090")
    monkeypatch.setattr(
        firebase.fb_auth,
        "verify_id_token",
        lambda token, check_revoked=False: {"uid": "abc"},
    )

    with pytest.raises(firebase.FirebasePhoneMissingError):
        firebase.verify_firebase_id_token("a.b.c")


def test_an_empty_token_is_refused_before_any_network_call(monkeypatch):
    with pytest.raises(firebase.FirebaseTokenMissingError):
        firebase.verify_firebase_id_token("   ")


def test_nothing_configured_at_all_still_raises(monkeypatch):
    """A misconfigured production deploy must fail loudly, not guess."""
    monkeypatch.setattr(settings, "FIREBASE_SERVICE_ACCOUNT_JSON", None)
    monkeypatch.setattr(settings, "FIREBASE_SERVICE_ACCOUNT_PATH", None)
    monkeypatch.setattr(settings, "FIREBASE_PROJECT_ID", None)
    monkeypatch.setattr(firebase.firebase_admin, "_apps", {})

    def _boom(*a, **k):
        raise RuntimeError("no application default credentials")

    monkeypatch.setattr(firebase.firebase_admin, "initialize_app", _boom)

    with pytest.raises(RuntimeError, match="FIREBASE_PROJECT_ID"):
        firebase.initialize_firebase()


def test_the_anonymous_credential_authenticates_nothing(monkeypatch):
    """It exists to satisfy client construction, not to grant access."""
    from google.auth.credentials import AnonymousCredentials

    credential = firebase._PublicCertsOnlyCredential().get_credential()
    assert isinstance(credential, AnonymousCredentials)
