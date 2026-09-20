from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.demo_limit import demo_rate_limit
from app.core.security import get_current_seller
from app.db.session import get_db
from app.models.seller import Seller
from app.schemas.approval import ListingApprovalRequest, ListingApprovalResponse
from app.schemas.consent import ListingConsentRequest, ListingConsentResponse
from app.schemas.enums import ListingState
from app.schemas.listing import (
    ListingAttentionResponse,
    ListingCreateRequest,
    ListingListResponse,
    ListingReadbackResponse,
    ListingResponse,
    ListingStatusResponse,
)
from app.schemas.preview import ListingPreviewResponse, ListingPublishResponse
from app.schemas.suggestion import (
    ListingSuggestionsResponse,
    SuggestionApprovalRequest,
    SuggestionApprovalResponse,
    SuggestionItem,
)
from app.services.listing_fields import (
    apply_field_values,
    result_for,
    settle_suggestion_for_field,
)
from app.services.listing_view import listing_image_urls, to_listing_response
from app.services.media_storage import save_media_upload
from app.schemas.enums import MediaType
from app.models.media import Media
from app.services.listing import (
    ListingNotFoundError,
    create_or_get_listing,
    delete_listing_for_seller,
    get_listing_for_seller,
    list_seller_listings,
    transition_listing,
)

router = APIRouter(prefix="/listings", tags=["Listings"])


@router.post(
    "",
    response_model=ListingResponse,
    status_code=status.HTTP_200_OK,
    summary="Create / Queue Listing",
    description="Create/queue a new listing item with a mobile client item identifier.",
    # Every accepted listing goes on to spend Sarvam and Gemini credit, and in
    # DEMO_MODE this endpoint takes no credentials. The cap is a no-op when
    # DEMO_MODE is off.
    dependencies=[Depends(demo_rate_limit)],
)
def create_listing(
    payload: ListingCreateRequest,
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> ListingResponse:
    listing = create_or_get_listing(
        db=db,
        seller_id=current_seller.id,
        client_item_id=payload.client_item_id,
        description=payload.description,
        photo_count=payload.photo_count,
    )
    return to_listing_response(listing)


@router.get(
    "",
    response_model=ListingListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Seller Listings",
    description="Return listings belonging to the current seller.",
)
def list_listings(
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> ListingListResponse:
    listings = list_seller_listings(db=db, seller_id=current_seller.id)
    return ListingListResponse(items=[to_listing_response(item) for item in listings])


@router.get(
    "/{listing_id}",
    response_model=ListingResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Listing",
    description="Fetch a listing by its server identifier.",
)
def get_listing(
    listing_id: str,
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> ListingResponse:
    listing = get_listing_for_seller(db=db, listing_id=listing_id, seller_id=current_seller.id)
    return to_listing_response(listing)


@router.delete(
    "/{listing_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Listing",
    description="Delete a listing and its media. Deleting one already gone is a no-op.",
)
def delete_listing(
    listing_id: str,
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> Response:
    try:
        delete_listing_for_seller(
            db=db, listing_id=listing_id, seller_id=current_seller.id
        )
    except ListingNotFoundError:
        # The seller asked for this to be gone and it is gone. Reporting 404 to a
        # phone retrying a delete it already made would strand the listing on the
        # device, so a repeated delete succeeds quietly.
        pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{listing_id}",
    response_model=ListingResponse,
    status_code=status.HTTP_200_OK,
    summary="Correct Listing Fields",
    description="Write artisan corrections onto the listing's fact sheet.",
)
def patch_listing(
    listing_id: str,
    changes: Dict[str, Any] = Body(...),
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> ListingResponse:
    listing = get_listing_for_seller(
        db=db, listing_id=listing_id, seller_id=current_seller.id
    )

    apply_field_values(db=db, listing=listing, changes=changes)
    for field in changes:
        settle_suggestion_for_field(db=db, listing=listing, field=field)

    db.commit()
    db.refresh(listing)
    return to_listing_response(listing)


@router.post(
    "/{listing_id}/answer",
    response_model=ListingResponse,
    status_code=status.HTTP_200_OK,
    summary="Answer A Question About A Listing",
    description=(
        "Accept the artisan's spoken reply, and the value it carries, for one "
        "field the pipeline could not fill."
    ),
)
async def answer_listing_question(
    listing_id: str,
    voiceReply: UploadFile = File(...),
    field: Optional[str] = Form(None),
    transcript: Optional[str] = Form(None),
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> ListingResponse:
    listing = get_listing_for_seller(
        db=db, listing_id=listing_id, seller_id=current_seller.id
    )

    # Keep the recording whatever else happens: it is the artisan's own words,
    # and a later run may transcribe it better than the phone did.
    stored = await save_media_upload(
        file=voiceReply, media_type=MediaType.audio, listing_id=listing_id
    )
    db.add(
        Media(
            id=stored.media_id,
            listing_id=listing.id,
            media_type=MediaType.audio,
            original_filename=stored.original_filename,
            storage_path=stored.storage_path,
            mime_type=stored.mime_type,
            file_size_bytes=stored.file_size_bytes,
        )
    )

    spoken = (transcript or "").strip()
    if field and spoken:
        apply_field_values(db=db, listing=listing, changes={field: spoken})
        settle_suggestion_for_field(db=db, listing=listing, field=field)

    # The question has been answered, so stop asking it.
    if spoken:
        result_for(db, listing).follow_up_question = None

    db.commit()
    db.refresh(listing)
    return to_listing_response(listing)


@router.get(
    "/{listing_id}/status",
    response_model=ListingStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Listing Pipeline Status",
    description="Return current processing state of the listing in the pipeline.",
)
def get_listing_status(
    listing_id: str,
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> ListingStatusResponse:
    listing = get_listing_for_seller(db=db, listing_id=listing_id, seller_id=current_seller.id)
    return ListingStatusResponse(
        listing_id=str(listing.id),
        state=listing.state,
    )


@router.get(
    "/{listing_id}/attention",
    response_model=ListingAttentionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Listing Attention Details",
    description="Return attention information when a listing requires artisan intervention.",
)
def get_listing_attention(
    listing_id: str,
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> ListingAttentionResponse:
    listing = get_listing_for_seller(db=db, listing_id=listing_id, seller_id=current_seller.id)
    result = listing.result
    return ListingAttentionResponse(
        listing_id=str(listing.id),
        needs_attention=(listing.state == ListingState.needs_attention),
        question=result.follow_up_question if result else None,
        field=None,
    )


@router.get(
    "/{listing_id}/readback",
    response_model=ListingReadbackResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Listing Read-back Details",
    description="Return generated listing information for artisan review and audio read-back.",
)
def get_listing_readback(
    listing_id: str,
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> ListingReadbackResponse:
    listing = get_listing_for_seller(db=db, listing_id=listing_id, seller_id=current_seller.id)
    result = listing.result
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This listing has not been processed yet, so there is nothing to read back.",
        )
    price = result.price_in_paise if result.price_in_paise is not None else result.suggested_price_in_paise
    return ListingReadbackResponse(
        listing_id=str(listing.id),
        language=result.language or current_seller.language or "hi",
        title=result.title or "",
        description=result.description or "",
        price=round(price / 100, 2) if price is not None else None,
        audio_url=None,
    )


@router.post(
    "/{listing_id}/approval",
    response_model=ListingApprovalResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit Listing Approval",
    description="Record artisan review approval/correction for generated listing data.",
)
def approve_listing(
    listing_id: str,
    payload: ListingApprovalRequest,
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> ListingApprovalResponse:
    listing = get_listing_for_seller(db=db, listing_id=listing_id, seller_id=current_seller.id)
    target_state = ListingState.ready if payload.approved else ListingState.needs_attention
    listing = transition_listing(db=db, listing=listing, new_state=target_state)
    return ListingApprovalResponse(
        listing_id=str(listing.id),
        approved=payload.approved,
        state=listing.state,
    )


@router.get(
    "/{listing_id}/suggestions",
    response_model=ListingSuggestionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Suggested Additions",
    description="Return non-binding suggested additions for artisan review.",
)
def get_listing_suggestions(
    listing_id: str,
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> ListingSuggestionsResponse:
    listing = get_listing_for_seller(db=db, listing_id=listing_id, seller_id=current_seller.id)
    return ListingSuggestionsResponse(
        items=[
            SuggestionItem(
                id=str(item.id),
                field=item.field,
                value=item.value,
                reason=item.reason,
            )
            for item in listing.suggestions
        ]
    )


@router.post(
    "/{listing_id}/suggestions/{suggestion_id}/approval",
    response_model=SuggestionApprovalResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve or Reject Suggestion",
    description="Explicitly approve or reject an individual suggested addition.",
)
def approve_suggestion(
    listing_id: str,
    suggestion_id: str,
    payload: SuggestionApprovalRequest,
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> SuggestionApprovalResponse:
    listing = get_listing_for_seller(db=db, listing_id=listing_id, seller_id=current_seller.id)

    # Record the decision. This used to echo the request back and persist
    # nothing, so the same suggestion was asked again on the next review.
    target = next(
        (s for s in listing.suggestions if str(s.id) == suggestion_id), None
    )
    if target is not None:
        target.approved = payload.approved
        db.add(target)
        db.commit()
    # An id this listing does not know is reported as settled rather than
    # refused: the app sends every decision in one go before publishing, and one
    # stale id must not be what stops an artisan publishing their work.

    return SuggestionApprovalResponse(
        listing_id=str(listing.id),
        suggestion_id=suggestion_id,
        approved=payload.approved,
    )


@router.post(
    "/{listing_id}/consent",
    response_model=ListingConsentResponse,
    status_code=status.HTTP_200_OK,
    summary="Record Artisan Consent",
    description="Record explicit permission to publish the artisan's photo and story.",
)
def record_listing_consent(
    listing_id: str,
    payload: ListingConsentRequest,
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> ListingConsentResponse:
    listing = get_listing_for_seller(db=db, listing_id=listing_id, seller_id=current_seller.id)
    return ListingConsentResponse(
        listing_id=str(listing.id),
        photo=payload.photo,
        story=payload.story,
        ready_to_publish=payload.photo and payload.story,
    )


@router.post(
    "/{listing_id}/publish",
    response_model=ListingPublishResponse,
    status_code=status.HTTP_200_OK,
    summary="Publish Listing",
    description="Trigger publication after approval and consent stages have completed.",
)
def publish_listing(
    listing_id: str,
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> ListingPublishResponse:
    listing = get_listing_for_seller(db=db, listing_id=listing_id, seller_id=current_seller.id)
    listing = transition_listing(db=db, listing=listing, new_state=ListingState.published)
    return ListingPublishResponse(
        listing_id=str(listing.id),
        state=listing.state,
        preview_url=None,
    )


@router.get(
    "/{listing_id}/preview",
    response_model=ListingPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Listing Preview",
    description="Return read-only listing preview data.",
)
def get_listing_preview(
    listing_id: str,
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> ListingPreviewResponse:
    listing = get_listing_for_seller(db=db, listing_id=listing_id, seller_id=current_seller.id)
    result = listing.result
    price = None
    if result is not None:
        paise = result.price_in_paise if result.price_in_paise is not None else result.suggested_price_in_paise
        price = round(paise / 100, 2) if paise is not None else None
    return ListingPreviewResponse(
        listing_id=str(listing.id),
        title=(result.title if result else None) or "",
        description=(result.description if result else None) or "",
        price=price,
        image_urls=listing_image_urls(listing),
    )
