"""Authentication API endpoints."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import AuthTokenResponse, FirebaseAuthRequest
from app.schemas.seller import SellerResponse
from app.services.auth import authenticate_firebase_user

router = APIRouter(tags=["Auth"])


@router.post(
    "/firebase",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate with Firebase ID Token",
    description="Verifies a Firebase phone-auth ID token, resolves or creates the corresponding seller, and returns an application JWT.",
)
def authenticate_firebase(
    payload: FirebaseAuthRequest,
    db: Session = Depends(get_db),
) -> AuthTokenResponse:
    access_token, seller = authenticate_firebase_user(payload.id_token, db)
    return AuthTokenResponse(
        access_token=access_token,
        token_type="bearer",
        seller=SellerResponse(
            id=str(seller.id),
            name=seller.name or "",
            language=seller.language or "hi",
            cluster=seller.cluster,
            ondc_seller_id=seller.ondc_seller_id,
            phone_number=seller.phone_number,
        ),
    )
