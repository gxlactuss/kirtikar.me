from pydantic import BaseModel, ConfigDict


class ListingConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    photo: bool
    story: bool


class ListingConsentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: str
    photo: bool
    story: bool
    ready_to_publish: bool
