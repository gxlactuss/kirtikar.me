from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict
from app.schemas.enums import ListingState


class ListingCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_item_id: str
    # Sent when the artisan typed the description instead of recording it.
    description: Optional[str] = None
    # How many photos the app is about to upload, so the pipeline waits for the
    # whole set rather than starting on the first one.
    photo_count: Optional[int] = None


class FactSheetResponse(BaseModel):
    """The fields the artisan reviews and corrects, one per card in the app."""

    model_config = ConfigDict(extra="forbid")

    material: Optional[str] = None
    size: Optional[str] = None
    colour: Optional[str] = None
    technique: Optional[str] = None
    origin: Optional[str] = None
    quantity: Optional[int] = None
    price_in_paise: Optional[int] = None
    hours_to_make: Optional[float] = None
    material_cost_in_paise: Optional[int] = None
    is_one_of_a_kind: bool = False


class SuggestionResponse(BaseModel):
    """One thing the run could not work out, phrased as a question."""

    model_config = ConfigDict(extra="forbid")

    id: str
    # Which fact sheet field this is about, so the app can open the right input
    # instead of offering a bare yes/no on something with no value attached.
    field: str
    spoken_prompt: str
    text_if_accepted: str
    approved: Optional[bool] = None


class ListingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    client_item_id: str
    state: ListingState

    # Everything below is what the pipeline understood. It is null until a run
    # finishes, which is what 'queued' and 'processing' mean to the app.
    title: Optional[str] = None
    description: Optional[str] = None
    image_urls: List[str] = []
    fact_sheet: FactSheetResponse = FactSheetResponse()
    suggestions: List[SuggestionResponse] = []
    follow_up_question: Optional[str] = None
    suggested_price_in_paise: Optional[int] = None
    price_floor_in_paise: Optional[int] = None
    preview_url: Optional[str] = None
    photo_consent: bool = False
    story_consent: bool = False
    views: int = 0
    used_live_model: bool = False


class ListingListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: List[ListingResponse]


class ListingStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: str
    state: ListingState


class ListingAttentionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: str
    needs_attention: bool
    question: Optional[str] = None
    field: Optional[str] = None


class ListingReadbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: str
    language: str
    title: str
    description: str
    price: Optional[float] = None
    audio_url: Optional[str] = None
