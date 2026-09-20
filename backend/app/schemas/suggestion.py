from typing import List
from pydantic import BaseModel, ConfigDict


class SuggestionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    field: str
    value: str
    reason: str


class ListingSuggestionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: List[SuggestionItem]


class SuggestionApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool


class SuggestionApprovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: str
    suggestion_id: str
    approved: bool
