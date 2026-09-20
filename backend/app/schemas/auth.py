from pydantic import BaseModel, ConfigDict
from app.schemas.seller import SellerResponse


class FirebaseAuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_token: str


class AuthTokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"
    seller: SellerResponse
