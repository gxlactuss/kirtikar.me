from pydantic import BaseModel, ConfigDict
from app.schemas.enums import MediaType


class MediaUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    listing_id: str
    media_type: MediaType
    status: str = "uploaded"
