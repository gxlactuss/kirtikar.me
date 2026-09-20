"""Tests for the /voice/demo multimodal tester endpoint."""
import io
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.llm.gemini import GeminiExtractionResult
from app.services.voice.pipeline import VoiceTranscriptionResult

CRAFT_IMAGE = (
    Path(__file__).resolve().parents[2] / "app" / "assets" / "images" / "crafts" / "metalwork.jpg"
)

AUDIO = ("note.wav", b"RIFF....WAVEfmt ....data....", "audio/wav")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_STORAGE_DIR", str(tmp_path / "media"))
    return TestClient(app)


@pytest.fixture
def stub_stations():
    """Stub both paid stations so the endpoint is exercised without network calls."""
    voice = VoiceTranscriptionResult(
        transcript="Clay water pot made on my wheel, two hundred and fifty rupees.",
        language_code="hi",
        duration_seconds=11.0,
        used_live_api=True,
    )
    extraction = GeminiExtractionResult(
        title="Handcrafted Terracotta Water Pot",
        craft_type="Terracotta Pottery",
        material="River clay",
        story_summary="Thrown on a traditional wheel.",
        stated_price=250.0,
        used_live_api=True,
    )
    with patch(
        "app.api.routes.voice_test.VoiceStation.process_audio", return_value=voice
    ), patch(
        "app.api.routes.voice_test.GeminiExtractor.extract_fact_sheet", return_value=extraction
    ) as mock_extract:
        yield mock_extract


def test_demo_runs_without_an_image(client, stub_stations):
    """The voice-only path stays supported; no image means no vision report."""
    response = client.post(
        "/api/v1/voice/demo",
        files={"file": (AUDIO[0], io.BytesIO(AUDIO[1]), AUDIO[2])},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["vision_station"] is None
    assert body["fact_sheet"]["image_used"] is False
    assert stub_stations.call_args.kwargs["image_path"] is None


@pytest.mark.skipif(not CRAFT_IMAGE.is_file(), reason="sample craft photo not available")
def test_uploaded_image_reaches_the_extractor_as_a_studio_cutout(client, stub_stations):
    """An uploaded photo must run through vision and be handed to the extractor.

    Previously the endpoint accepted audio only and captioned the listing with a
    hardcoded stock photo URL, so the advertised multimodal path never ran.
    """
    response = client.post(
        "/api/v1/voice/demo",
        files={
            "file": (AUDIO[0], io.BytesIO(AUDIO[1]), AUDIO[2]),
            "image": ("craft.jpg", CRAFT_IMAGE.read_bytes(), "image/jpeg"),
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert body["vision_station"]["quality_passed"] is True
    assert body["fact_sheet"]["image_used"] is True

    passed_image = stub_stations.call_args.kwargs["image_path"]
    assert passed_image is not None
    assert passed_image.endswith("_clean.jpg"), "extractor should receive the studio cutout"
    assert Path(passed_image).is_file(), "generated assets must outlive the request"


@pytest.mark.skipif(not CRAFT_IMAGE.is_file(), reason="sample craft photo not available")
def test_syndication_uses_the_uploaded_photo_not_a_stock_url(client, stub_stations):
    response = client.post(
        "/api/v1/voice/demo",
        files={
            "file": (AUDIO[0], io.BytesIO(AUDIO[1]), AUDIO[2]),
            "image": ("craft.jpg", CRAFT_IMAGE.read_bytes(), "image/jpeg"),
        },
    )

    payload = response.json()["syndication"]["google_merchant"]["details"]["content_api_payload"]
    assert "unsplash.com" not in payload["image_link"]
    assert payload["image_link"].endswith("_clean.jpg")


def test_live_api_flags_report_actual_usage_not_key_presence(client):
    """A configured key that fails must not be reported as a live call.

    The flags used to echo `bool(api_key)`, so a broken key produced a confident
    response built entirely from the canned fallback.
    """
    with patch(
        "app.api.routes.voice_test.VoiceStation.process_audio",
        return_value=VoiceTranscriptionResult(
            transcript="fallback text", language_code="hi", duration_seconds=0.0, used_live_api=False
        ),
    ), patch(
        "app.api.routes.voice_test.GeminiExtractor.extract_fact_sheet",
        return_value=GeminiExtractionResult(
            title="t", craft_type="c", material="m", story_summary="s", used_live_api=False
        ),
    ):
        response = client.post(
            "/api/v1/voice/demo",
            files={"file": (AUDIO[0], io.BytesIO(AUDIO[1]), AUDIO[2])},
            data={"sarvam_key": "a-key-that-fails", "gemini_key": "another-bad-key"},
        )

    body = response.json()
    assert body["voice_station"]["live_api_used"] is False
    assert body["fact_sheet"]["live_api_used"] is False
