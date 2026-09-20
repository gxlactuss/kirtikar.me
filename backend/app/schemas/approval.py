from pydantic import BaseModel, ConfigDict
from app.schemas.enums import ListingState


class ListingApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool


class ListingApprovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: str
    approved: bool
    state: ListingState
