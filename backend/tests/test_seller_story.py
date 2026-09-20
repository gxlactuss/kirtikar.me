"""The artisan's profile story as background for the listing description.

The story is written once and reused across a seller's listings, so it must
colour the copy without ever becoming a claim about the piece in front of it.
"""
import uuid

import pytest

from app.services.llm.gemini import GeminiExtractor
from app.services.pipeline.context import (
    ImageStageOutput,
    PipelineContext,
    SpeechStageOutput,
)
from app.services.pipeline.stages.fact_sheet import FactSheetStage

STORY = "I learned blue pottery from my grandmother in Jaipur and have worked at it for thirty years."


def _request(extractor, **kwargs):
    """Capture the whole request the extractor would send, without calling out."""
    sent = {}
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
                                    "text": (
                                        '{"title":"Blue Pottery Vase","craft_type":"Blue Pottery",'
                                        '"material":"Quartz clay","story_summary":"A vase."}'
                                    )
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
            sent.update(json or {})
            captured["url"] = url
            captured["headers"] = dict(headers or {})
            return _Response()

    import app.services.llm.gemini as module

    original = module.httpx.Client
    module.httpx.Client = lambda *a, **k: _Client()
    try:
        extractor.extract_fact_sheet(**kwargs)
    finally:
        module.httpx.Client = original
    captured["json"] = sent
    return captured


def _payload(extractor, **kwargs):
    """Just the request body, for the prompt-content assertions."""
    return _request(extractor, **kwargs)["json"]


def _prompt_text(payload):
    parts = payload["contents"][0]["parts"]
    return "\n".join(p["text"] for p in parts if "text" in p)


def test_the_story_reaches_the_model_when_the_artisan_wrote_one():
    extractor = GeminiExtractor(api_key="test-key", model_name="gemini-test")
    payload = _payload(
        extractor,
        transcript="This is a blue vase.",
        seller_story=STORY,
    )
    assert "thirty years" in _prompt_text(payload)


def test_nothing_about_a_story_is_sent_when_there_is_none():
    extractor = GeminiExtractor(api_key="test-key", model_name="gemini-test")
    payload = _payload(extractor, transcript="This is a blue vase.")
    prompt = _prompt_text(payload)
    assert "profile story" not in prompt


def test_a_blank_story_is_treated_as_no_story():
    extractor = GeminiExtractor(api_key="test-key", model_name="gemini-test")
    payload = _payload(
        extractor,
        transcript="This is a blue vase.",
        seller_story="   \n  ",
    )
    assert "profile story" not in _prompt_text(payload)


def test_a_long_story_is_capped_so_it_cannot_crowd_out_the_voice_note():
    extractor = GeminiExtractor(api_key="test-key", model_name="gemini-test")
    payload = _payload(
        extractor,
        transcript="This is a blue vase.",
        seller_story="word " * 400,
    )
    prompt = _prompt_text(payload)
    assert "…" in prompt
    assert len(prompt) < 2000


def test_the_model_is_told_the_story_may_not_change_product_facts():
    extractor = GeminiExtractor(api_key="test-key", model_name="gemini-test")
    payload = _payload(
        extractor,
        transcript="This is a blue vase.",
        seller_story=STORY,
    )
    instruction = payload["system_instruction"]["parts"][0]["text"].lower()
    assert "one short clause" in instruction
    assert "must not change" in instruction


def test_the_stage_passes_the_sellers_story_to_the_extractor():
    seen = {}

    class _Extractor:
        def extract_fact_sheet(
            self,
            transcript,
            detected_language="hi",
            image_path=None,
            seller_story=None,
            allow_synthetic_fallback=True,
        ):
            seen["story"] = seller_story
            return type(
                "R",
                (),
                {
                    "title": "t",
                    "craft_type": "c",
                    "material": "m",
                    "story_summary": "s",
                    "colors": [],
                    "dimensions": None,
                    "origin": None,
                    "attributes": {},
                },
            )()

    import app.services.pipeline.stages.fact_sheet as module

    module._gemini_extractor_instance = _Extractor()
    try:
        context = PipelineContext(listing_id=uuid.uuid4(), seller_story=STORY)
        context.image_output = ImageStageOutput(
            image_count=1, image_paths=["a.jpg"], detected_labels=[]
        )
        context.speech_output = SpeechStageOutput(
            audio_path="a.m4a", transcript="a blue vase", language="hi"
        )
        FactSheetStage().run(context)
    finally:
        module._gemini_extractor_instance = None

    assert seen["story"] == STORY
