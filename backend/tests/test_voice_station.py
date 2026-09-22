"""The voice note is what the artisan said, or an honest request to say it again.

These pin two regressions that together meant no real voice note was ever
heard: the station called Sarvam's legacy /speech-to-text-translate endpoint
with a model it does not serve, and every resulting error was covered by a
canned transcript about a Madhubani painting.
"""
import io
import uuid
import wave

import httpx
import pytest

from app.models.media import Media
from app.schemas.enums import MediaType
from app.services.pipeline.context import PipelineContext
from app.services.pipeline.result import StageStatus
from app.services.pipeline.stages import speech as speech_stage
from app.services.pipeline.stages.speech import SpeechStage
from app.services.voice import pipeline as voice
from app.services.voice.pipeline import VoiceStation


def _wav(seconds: float, rate: int = 16_000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


class _Recorder:
    """Stands in for httpx.Client, replaying scripted responses in order."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, headers=None, files=None, data=None):
        self.calls.append({"url": url, "data": data, "files": files})
        status, body = self.responses.pop(0)
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))


@pytest.fixture
def audio_file(tmp_path):
    path = tmp_path / "voice.wav"
    path.write_bytes(_wav(4.0))
    return path


def _station(monkeypatch, responses):
    recorder = _Recorder(responses)
    monkeypatch.setattr(voice.httpx, "Client", recorder)
    monkeypatch.setattr(voice.time, "sleep", lambda s: None)
    return VoiceStation(api_key="test-key"), recorder


def test_calls_the_v3_endpoint_in_translate_mode(monkeypatch, audio_file):
    station, recorder = _station(
        monkeypatch, [(200, {"transcript": "A clay pot from Khurja.", "language_code": "hi-IN"})]
    )

    result = station.process_audio(audio_file, allow_synthetic_fallback=False)

    call = recorder.calls[0]
    assert call["url"] == "https://api.sarvam.ai/speech-to-text"
    assert call["data"]["model"] == "saaras:v3"
    assert call["data"]["mode"] == "translate"
    assert result.transcript == "A clay pot from Khurja."
    assert result.language_code == "hi-IN"
    assert result.used_live_api is True
    # The new endpoint reports no duration, so it is read from the WAV header.
    assert result.duration_seconds == pytest.approx(4.0)


def test_a_note_over_the_rest_limit_is_trimmed_not_rejected(monkeypatch, tmp_path):
    long_note = tmp_path / "long.wav"
    long_note.write_bytes(_wav(30.2))
    station, recorder = _station(monkeypatch, [(200, {"transcript": "Hello."})])

    result = station.process_audio(long_note, allow_synthetic_fallback=False)

    sent = recorder.calls[0]["files"]["file"][1]
    with wave.open(io.BytesIO(sent)) as w:
        assert w.getnframes() / w.getframerate() < 30.0
    assert result.duration_seconds < 30.0


def test_a_busy_service_is_retried(monkeypatch, audio_file):
    station, recorder = _station(
        monkeypatch, [(429, {"error": "rate"}), (200, {"transcript": "A brass lamp."})]
    )
    assert station.process_audio(audio_file, allow_synthetic_fallback=False).transcript == "A brass lamp."
    assert len(recorder.calls) == 2


def test_a_rejected_request_is_an_error_not_a_painting(monkeypatch, audio_file):
    station, _ = _station(monkeypatch, [(400, {"error": "bad model"})])
    with pytest.raises(voice.VoiceServiceError):
        station.process_audio(audio_file, allow_synthetic_fallback=False)


def test_silence_is_reported_as_silence(monkeypatch, audio_file):
    station, _ = _station(monkeypatch, [(200, {"transcript": "   "})])
    with pytest.raises(voice.NoSpeechError):
        station.process_audio(audio_file, allow_synthetic_fallback=False)


# ---------------- the stage ----------------


def _context(tmp_path, monkeypatch, typed=None) -> PipelineContext:
    storage = tmp_path / "media"
    monkeypatch.setattr("app.core.config.settings.MEDIA_STORAGE_DIR", str(storage))
    listing_id = uuid.uuid4()
    rel = f"{listing_id}/voice.wav"
    (storage / str(listing_id)).mkdir(parents=True)
    (storage / rel).write_bytes(_wav(3.0))
    media = Media(id=uuid.uuid4(), listing_id=listing_id, media_type=MediaType.audio, storage_path=rel)
    return PipelineContext(listing_id=listing_id, media=[media], typed_description=typed)


def _with_station(monkeypatch, responses):
    station, _ = _station(monkeypatch, responses)
    monkeypatch.setattr(speech_stage, "_get_voice_station", lambda: station)


def test_stage_uses_what_was_said(tmp_path, monkeypatch):
    ctx = _context(tmp_path, monkeypatch)
    _with_station(monkeypatch, [(200, {"transcript": "A bamboo basket, 300 rupees."})])

    res = SpeechStage().run(ctx)

    assert res.status == StageStatus.success
    assert ctx.speech_output.transcript == "A bamboo basket, 300 rupees."


def test_stage_never_invents_a_transcript_for_a_real_recording(tmp_path, monkeypatch):
    ctx = _context(tmp_path, monkeypatch)
    _with_station(monkeypatch, [(403, {}), (403, {})])

    res = SpeechStage().run(ctx)

    assert res.status == StageStatus.failure
    assert ctx.speech_output is None
    assert "Madhubani" not in (res.reason or "")


def test_stage_asks_again_when_nothing_was_heard(tmp_path, monkeypatch):
    ctx = _context(tmp_path, monkeypatch)
    _with_station(monkeypatch, [(200, {"transcript": ""})])

    res = SpeechStage().run(ctx)

    assert res.status == StageStatus.needs_attention
    assert "could not hear" in res.reason.lower()


def test_stage_falls_back_to_the_typed_description(tmp_path, monkeypatch):
    ctx = _context(tmp_path, monkeypatch, typed="A carved wooden elephant.")
    _with_station(monkeypatch, [(503, {}), (503, {})])

    res = SpeechStage().run(ctx)

    assert res.status == StageStatus.success
    assert ctx.speech_output.transcript == "A carved wooden elephant."
    assert res.metadata["source"] == "typed"
