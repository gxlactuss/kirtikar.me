from typing import Optional
from pydantic import BaseModel, ConfigDict


class SellerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str = ""
    language: str = "hi"
    cluster: Optional[str] = None
    ondc_seller_id: Optional[str] = None
    phone_number: Optional[str] = None
    craft_story: Optional[str] = None


class SellerUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    language: Optional[str] = None
    cluster: Optional[str] = None
    craft_story: Optional[str] = None
