from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from app.schemas.enums import ListingState


class ListingPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: str
    title: str
    description: str
    price: Optional[float] = None
    image_urls: List[str] = []


class ListingPublishResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: str
    state: ListingState
    preview_url: Optional[str] = None
