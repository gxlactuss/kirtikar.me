"""The seam between the vision station and the language model.

Every test here covers something the rest of the suite could not see, because
the existing fixtures have no image bytes on disk: with no real files the image
stage takes its synthetic branch and the fact sheet stage never builds a real
request. These use actual photographs in a temporary media root so the live
path is exercised.
"""
import uuid
from pathlib import Path

import httpx
import numpy as np
import pytest
from PIL import Image

from app.core.config import settings
from app.models.media import Media
from app.schemas.enums import MediaType
from app.services.llm.gemini import (
    DEFAULT_IMAGE_MIME_TYPE,
    GeminiExtractor,
    image_mime_type,
)
from app.services.pipeline.context import (
    ImageStageOutput,
    PipelineContext,
    SpeechStageOutput,
)
from app.services.pipeline.result import StageStatus
from app.services.pipeline.stages import image as image_stage_module
from app.services.pipeline.stages.fact_sheet import FactSheetStage, _primary_image_path
from app.services.pipeline.stages.image import ImageStage

CRAFT_IMAGES = Path(__file__).resolve().parents[2] / "app" / "assets" / "images" / "crafts"

# A cutout of a single clear object is what the subject gate is looking for;
# the craft category photos are lifestyle scenes and are rightly refused.
PRODUCT_PHOTO = "jewellery"


@pytest.fixture
def media_root(tmp_path, monkeypatch):
    root = tmp_path / "media-root"
    (root / "media").mkdir(parents=True)
    monkeypatch.setattr(settings, "MEDIA_STORAGE_DIR", str(root))
    return root


def _place_photo(media_root: Path, name: str = PRODUCT_PHOTO) -> Media:
    """Copy a real craft photograph in as an uploaded image."""
    source = CRAFT_IMAGES / f"{name}.jpg"
    if not source.is_file():
        pytest.skip(f"sample craft photo not available: {source}")
    media_id = uuid.uuid4()
    subpath = f"media/{media_id}.jpg"
    (media_root / subpath).write_bytes(source.read_bytes())
    return Media(
        id=media_id,
        listing_id=uuid.uuid4(),
        media_type=MediaType.image,
        storage_path=subpath,
    )


def _speech() -> SpeechStageOutput:
    return SpeechStageOutput(
        audio_path="voice.m4a",
        transcript="A silver necklace I made by hand. It is 40 centimetres long.",
        language="hi",
    )


class _RecordingExtractor:
    """Stands in for Gemini and remembers what it was asked."""

    def __init__(self):
        self.calls = []

    def extract_fact_sheet(
        self,
        transcript,
        detected_language="hi",
        image_path=None,
        seller_story=None,
        allow_synthetic_fallback=True,
    ):
        from app.services.llm.gemini import GeminiExtractionResult

        self.calls.append({"transcript": transcript, "image_path": image_path})
        return GeminiExtractionResult(
            title="Handmade Silver Necklace",
            craft_type="Silver Filigree",
            material="Silver",
            story_summary="A necklace.",
            used_live_api=True,
        )


# --------------------------------------------------------------------------
# The photograph has to reach the model
# --------------------------------------------------------------------------


def test_the_processed_photo_is_handed_to_the_model(media_root, monkeypatch):
    """The whole point of the vision stage is to inform the extraction.

    The fact sheet stage used to call the extractor without an image at all, so
    every listing was written from the voice note alone and the cutout the
    station worked to produce was never looked at.
    """
    media = _place_photo(media_root)
    context = PipelineContext(listing_id=media.listing_id, media=[media])

    assert ImageStage().run(context).status == StageStatus.success

    extractor = _RecordingExtractor()
    monkeypatch.setattr(
        "app.services.pipeline.stages.fact_sheet._get_gemini_extractor",
        lambda: extractor,
    )
    context.speech_output = _speech()

    assert FactSheetStage().run(context).status == StageStatus.success

    sent = extractor.calls[0]["image_path"]
    assert sent is not None, "the photograph never reached the model"
    assert Path(sent).is_file()
    # Specifically the composited studio image, not the raw camera frame.
    assert sent.endswith("_clean.jpg")


def test_the_studio_composite_is_preferred_over_the_raw_upload(media_root):
    media = _place_photo(media_root)
    processed = media_root / str(media.listing_id) / "vision" / "x_clean.jpg"
    processed.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1024, 1024), "white").save(processed)

    context = PipelineContext(listing_id=media.listing_id, media=[media])
    context.image_output = ImageStageOutput(
        image_count=1,
        image_paths=[str(processed.relative_to(media_root))],
        detected_labels=[],
    )

    assert _primary_image_path(context, media_root.resolve()) == str(processed.resolve())


def test_the_original_upload_is_used_when_there_is_no_composite(media_root):
    media = _place_photo(media_root)
    context = PipelineContext(listing_id=media.listing_id, media=[media])

    chosen = _primary_image_path(context, media_root.resolve())
    assert chosen == str((media_root / media.storage_path).resolve())


def test_synthetic_fixtures_still_report_no_image(media_root):
    """A path with no bytes behind it must not be offered to the model."""
    context = PipelineContext(listing_id=uuid.uuid4())
    context.image_output = ImageStageOutput(
        image_count=1, image_paths=["nothing/here.jpg"], detected_labels=[]
    )
    assert _primary_image_path(context, media_root.resolve()) is None


def test_a_path_escaping_the_media_root_is_refused(media_root, tmp_path):
    """A stored path must never pull an arbitrary host file into an API call."""
    outside = tmp_path / "secret.jpg"
    Image.new("RGB", (8, 8), "white").save(outside)

    context = PipelineContext(listing_id=uuid.uuid4())
    context.image_output = ImageStageOutput(
        image_count=1,
        image_paths=["../secret.jpg", str(outside)],
        detected_labels=[],
    )
    assert _primary_image_path(context, media_root.resolve()) is None


# --------------------------------------------------------------------------
# The image stage must not lose or misreport a photo
# --------------------------------------------------------------------------


def test_reported_dimensions_match_the_file_on_disk(media_root):
    media = _place_photo(media_root)
    context = PipelineContext(listing_id=media.listing_id, media=[media])

    assert ImageStage().run(context).status == StageStatus.success

    for path, dims in zip(
        context.image_output.image_paths, context.image_output.dimensions
    ):
        with Image.open(media_root / path) as img:
            assert dims == {"width": img.width, "height": img.height}


def test_a_broken_vision_install_fails_instead_of_publishing_raw_photos(
    media_root, monkeypatch
):
    """No station plus real files used to fall through to the fixture branch.

    That quietly emitted the artisan's unprocessed camera frames as though they
    had been graded and composited.
    """
    media = _place_photo(media_root)
    monkeypatch.setattr(image_stage_module, "_get_station", lambda: None)

    result = ImageStage().run(PipelineContext(listing_id=media.listing_id, media=[media]))

    assert result.status == StageStatus.failure
    assert "unavailable" in result.reason.lower()


def test_a_missing_composite_fails_rather_than_dropping_the_photo(
    media_root, monkeypatch
):
    """Fewer images out than in would silently shrink the artisan's listing."""
    media = _place_photo(media_root)

    class _SilentStation:
        def process_image(self, input_path, output_dir, item_id=None):
            return {
                "quality": {"passed": True, "warnings": []},
                "subject": {"passed": True, "warnings": []},
                "outputs": {},
            }

    monkeypatch.setattr(image_stage_module, "_get_station", lambda: _SilentStation())

    result = ImageStage().run(PipelineContext(listing_id=media.listing_id, media=[media]))
    assert result.status == StageStatus.failure


def test_a_rejected_photo_still_reports_why(media_root, monkeypatch):
    """The quality numbers are the only way to debug a rejection after the fact."""
    media = _place_photo(media_root)

    class _RejectingStation:
        def process_image(self, input_path, output_dir, item_id=None):
            return {
                "quality": {
                    "passed": False,
                    "blur_score": 4.0,
                    "warnings": ["Image is too blurry"],
                },
                "subject": None,
                "outputs": {},
            }

    monkeypatch.setattr(image_stage_module, "_get_station", lambda: _RejectingStation())

    context = PipelineContext(listing_id=media.listing_id, media=[media])
    result = ImageStage().run(context)
    assert result.status == StageStatus.success
    assert result.metadata["quality_reports"][0]["blur_score"] == 4.0
    assert "too blurry" in context.photo_warnings[0].lower()


def test_a_blurry_photo_is_turned_back_before_any_segmentation(media_root):
    """The gate must flag a genuinely unusable photo for retake, end to end."""
    source = CRAFT_IMAGES / f"{PRODUCT_PHOTO}.jpg"
    if not source.is_file():
        pytest.skip("sample craft photo not available")

    media_id = uuid.uuid4()
    subpath = f"media/{media_id}.jpg"
    with Image.open(source) as img:
        tiny = img.convert("RGB").resize((24, 24)).resize(img.size)
        tiny.save(media_root / subpath)
    media = Media(
        id=media_id,
        listing_id=uuid.uuid4(),
        media_type=MediaType.image,
        storage_path=subpath,
    )

    context = PipelineContext(listing_id=media.listing_id, media=[media])
    result = ImageStage().run(context)
    assert result.status == StageStatus.success
    assert context.photo_warnings
    warning = context.photo_warnings[0].lower()
    assert "quality" in warning or "blur" in warning
    # Nothing was composited from it, so the listing keeps serving the raw frame.
    assert media.processed_path is None


# --------------------------------------------------------------------------
# How the request is built
# --------------------------------------------------------------------------


def _capture_request(extractor, **kwargs):
    captured = {}

    class _Response:
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": '{"title":"T","craft_type":"C",'
                                    '"material":"M","story_summary":"S"}'
                                }
                            ]
                        }
                    }
                ]
            }

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = dict(headers or {})
            return _Response()

    import app.services.llm.gemini as module

    original = module.httpx.Client
    module.httpx.Client = lambda *a, **k: _Client()
    try:
        extractor.extract_fact_sheet(**kwargs)
    finally:
        module.httpx.Client = original
    return captured


def test_the_api_key_never_appears_in_the_url():
    """httpx logs the full URL at INFO, so a key in the query string is a leak."""
    extractor = GeminiExtractor(api_key="super-secret-key", model_name="gemini-test")
    request = _capture_request(extractor, transcript="A blue vase.")

    assert "super-secret-key" not in request["url"]
    assert "key=" not in request["url"]
    assert request["headers"]["x-goog-api-key"] == "super-secret-key"


def test_the_image_is_attached_as_inline_data(media_root):
    photo = media_root / "shot.png"
    Image.new("RGB", (16, 16), "white").save(photo)

    extractor = GeminiExtractor(api_key="k", model_name="gemini-test")
    request = _capture_request(
        extractor, transcript="A blue vase.", image_path=str(photo)
    )

    parts = request["json"]["contents"][0]["parts"]
    inline = [p for p in parts if "inline_data" in p]
    assert len(inline) == 1
    assert inline[0]["inline_data"]["mime_type"] == "image/png"
    assert inline[0]["inline_data"]["data"]


@pytest.mark.parametrize(
    "name,expected",
    [
        ("photo.jpg", "image/jpeg"),
        ("photo.JPEG", "image/jpeg"),
        ("photo.png", "image/png"),
        ("photo.PNG", "image/png"),
        # Phone cameras hand us these constantly; calling them JPEG made Gemini
        # reject the image and quietly drop it from the request.
        ("photo.webp", "image/webp"),
        ("photo.heic", "image/heic"),
        ("photo.heif", "image/heif"),
        ("photo.gif", "image/gif"),
        ("photo.unknown", DEFAULT_IMAGE_MIME_TYPE),
        ("noextension", DEFAULT_IMAGE_MIME_TYPE),
    ],
)
def test_extensions_map_to_the_right_mime_type(name, expected):
    assert image_mime_type(name) == expected


def test_a_missing_image_file_is_simply_left_out():
    extractor = GeminiExtractor(api_key="k", model_name="gemini-test")
    request = _capture_request(
        extractor, transcript="A blue vase.", image_path="/no/such/photo.jpg"
    )
    parts = request["json"]["contents"][0]["parts"]
    assert not [p for p in parts if "inline_data" in p]


# --------------------------------------------------------------------------
# Transient failures
# --------------------------------------------------------------------------


def _extractor_with_responses(statuses, monkeypatch):
    """A client that returns the given statuses in order, then succeeds."""
    attempts = {"count": 0}

    class _Response:
        def __init__(self, status):
            self.status_code = status
            self.text = "busy"

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "err", request=httpx.Request("POST", "http://x"), response=self
                )

        @staticmethod
        def json():
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": '{"title":"T","craft_type":"C",'
                                    '"material":"M","story_summary":"S"}'
                                }
                            ]
                        }
                    }
                ]
            }

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def post(self, url, json=None, headers=None):
            i = attempts["count"]
            attempts["count"] += 1
            return _Response(statuses[i] if i < len(statuses) else 200)

    import app.services.llm.gemini as module

    monkeypatch.setattr(module.httpx, "Client", lambda *a, **k: _Client())
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)
    return attempts


def _single_model(**kw):
    """An extractor pinned to one model, so attempt counts are unambiguous."""
    return GeminiExtractor(
        api_key="k", model_name="gemini-test", fallback_models=[], **kw
    )


def test_a_503_is_retried_rather_than_abandoned(monkeypatch):
    """The first live call of a session routinely draws a 503 on the Flash tier."""
    attempts = _extractor_with_responses([503], monkeypatch)

    result = _single_model(max_attempts=2).extract_fact_sheet(
        transcript="A blue vase.", allow_synthetic_fallback=False
    )

    assert attempts["count"] == 2
    assert result.used_live_api is True


def test_an_overloaded_model_falls_through_to_the_next_one(monkeypatch):
    """A lighter model writing the listing beats canned facts writing it."""
    # The first model is overloaded; with a spare in the chain it is not
    # retried, because its 503 takes ~45s to arrive. The spare answers.
    attempts = _extractor_with_responses([503], monkeypatch)
    extractor = GeminiExtractor(
        api_key="k",
        model_name="busy-model",
        fallback_models=["spare-model"],
        max_attempts=2,
    )

    result = extractor.extract_fact_sheet(
        transcript="A blue vase.", allow_synthetic_fallback=True
    )

    assert attempts["count"] == 2
    assert result.used_live_api is True, "should have used the fallback model, not canned facts"


def test_the_model_chain_is_ordered_and_deduplicated():
    extractor = GeminiExtractor(
        api_key="k",
        model_name="primary",
        fallback_models=["primary", "spare", "spare", ""],
    )
    assert extractor._model_chain() == ["primary", "spare"]


def test_every_model_exhausted_falls_back_to_canned_facts(monkeypatch):
    attempts = _extractor_with_responses([503] * 10, monkeypatch)
    extractor = GeminiExtractor(
        api_key="k",
        model_name="busy-one",
        fallback_models=["busy-two"],
        max_attempts=2,
    )

    result = extractor.extract_fact_sheet(
        transcript="A blue vase.", allow_synthetic_fallback=True
    )

    # One try on the first model, and the last model in the chain keeps its
    # second attempt.
    assert attempts["count"] == 3
    # used_live_api stays False so a caller can tell a working demo from a
    # silent failure.
    assert result.used_live_api is False


def test_persistent_failure_raises_when_fallback_is_disabled(monkeypatch):
    _extractor_with_responses([503] * 10, monkeypatch)

    with pytest.raises(httpx.HTTPStatusError):
        _single_model(max_attempts=2).extract_fact_sheet(
            transcript="A blue vase.", allow_synthetic_fallback=False
        )


def test_a_bad_request_is_not_retried(monkeypatch):
    """A 400 means the request itself is wrong; repeating it just wastes time."""
    attempts = _extractor_with_responses([400], monkeypatch)

    _single_model(max_attempts=3).extract_fact_sheet(
        transcript="A blue vase.", allow_synthetic_fallback=True
    )
    assert attempts["count"] == 1
