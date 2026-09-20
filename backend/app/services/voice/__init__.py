"""Voice and speech recognition subsystem package."""
from app.services.voice.pipeline import VoiceStation, VoiceTranscriptionResult

__all__ = ["VoiceStation", "VoiceTranscriptionResult"]
