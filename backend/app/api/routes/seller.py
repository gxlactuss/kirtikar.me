from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.security import get_current_seller
from app.db.session import get_db
from app.models.seller import Seller
from app.schemas.seller import SellerResponse, SellerUpdateRequest

router = APIRouter(prefix="/seller", tags=["Seller"])


@router.get(
    "",
    response_model=SellerResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Seller Profile",
    description="Return the profile of the currently authenticated seller.",
)
def get_seller(
    current_seller: Seller = Depends(get_current_seller),
) -> SellerResponse:
    return SellerResponse(
        id=str(current_seller.id),
        name=current_seller.name or "",
        language=current_seller.language or "hi",
        cluster=current_seller.cluster,
        ondc_seller_id=current_seller.ondc_seller_id,
        phone_number=current_seller.phone_number,
        craft_story=current_seller.craft_story,
    )


@router.put(
    "",
    response_model=SellerResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Seller Profile",
    description="Update profile fields (name, language, cluster, craft story) for the currently authenticated seller.",
)
def update_seller(
    payload: SellerUpdateRequest,
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> SellerResponse:
    if payload.name is not None:
        current_seller.name = payload.name
    if payload.language is not None:
        current_seller.language = payload.language
    if payload.cluster is not None:
        current_seller.cluster = payload.cluster
    if payload.craft_story is not None:
        # Empty string clears it, so an artisan can take their story back down.
        story = payload.craft_story.strip()
        current_seller.craft_story = story or None

    db.commit()
    db.refresh(current_seller)

    return SellerResponse(
        id=str(current_seller.id),
        name=current_seller.name or "",
        language=current_seller.language or "hi",
        cluster=current_seller.cluster,
        ondc_seller_id=current_seller.ondc_seller_id,
        phone_number=current_seller.phone_number,
        craft_story=current_seller.craft_story,
    )
