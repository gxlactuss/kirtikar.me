from enum import Enum


class ListingState(str, Enum):
    """Listing lifecycle states as defined in the architectural state machine."""
    queued = "queued"
    processing = "processing"
    needs_attention = "needs_attention"
    ready = "ready"
    published = "published"


class MediaType(str, Enum):
    """Supported media upload types."""
    image = "image"
    audio = "audio"
