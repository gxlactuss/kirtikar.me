import uuid
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_seller
from app.db.session import get_db
from app.models.listing import Listing
from app.models.media import Media
from app.models.seller import Seller
from app.schemas.enums import ListingState, MediaType
from app.schemas.media import MediaUploadResponse
from app.services.media_storage import delete_stored_file, save_media_upload
from app.workers.listing_pipeline import process_listing

router = APIRouter(prefix="/listings", tags=["Media"])


@router.post(
    "/{listing_id}/media",
    response_model=MediaUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload Listing Media",
    description="Upload media (image or audio) associated with a listing using multipart/form-data.",
)
async def upload_listing_media(
    listing_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    media_type: MediaType = Form(...),
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> MediaUploadResponse:
    # 1. Validate and store media file on local disk
    stored = await save_media_upload(
        file=file,
        media_type=media_type,
        listing_id=listing_id,
    )

    # 2. Listing persistence seam (Task 6 boundary)
    # If the listing exists in the database, associate Media and check seller ownership.
    # If listing persistence is still stubbed (e.g. unpersisted id), preserve the stub seam.
    listing_uuid: Optional[uuid.UUID] = None
    try:
        listing_uuid = uuid.UUID(listing_id)
    except (ValueError, TypeError, AttributeError):
        pass

    if listing_uuid is not None:
        db_listing = db.query(Listing).filter(Listing.id == listing_uuid).first()
        if db_listing is not None:
            # Enforce seller ownership if listing exists in DB
            if db_listing.seller_id != current_seller.id:
                delete_stored_file(stored.dest_path)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Listing does not belong to authenticated seller.",
                )

            # Persist Media metadata record
            media_record = Media(
                id=stored.media_id,
                listing_id=db_listing.id,
                media_type=media_type,
                original_filename=stored.original_filename,
                storage_path=stored.storage_path,
                mime_type=stored.mime_type,
                file_size_bytes=stored.file_size_bytes,
            )
            try:
                db.add(media_record)
                db.commit()
                db.refresh(media_record)
            except Exception as exc:
                db.rollback()
                delete_stored_file(stored.dest_path)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to persist media metadata.",
                ) from exc

            # The pipeline needs a photo and an account of the piece, and the
            # app uploads files one at a time, so start it on the upload that
            # completes the set. The account is normally a voice note, but the
            # description step also offers a keyboard, and a typed note arrives
            # with the listing rather than as a file - without this a typed
            # description left the listing queued forever.
            # Queued and needs_attention are the only states it may enter from; the
            # runner rejects the rest, which keeps repeat uploads from racing it.
            if db_listing.state in (ListingState.queued, ListingState.needs_attention):
                uploaded = [
                    row[0]
                    for row in db.query(Media.media_type).filter(
                        Media.listing_id == db_listing.id
                    )
                ]
                photo_count = sum(1 for kind in uploaded if kind == MediaType.image)
                has_photo = photo_count > 0
                has_audio = MediaType.audio in uploaded
                has_account = has_audio or bool(
                    (db_listing.typed_description or "").strip()
                )
                # Waiting for the whole set matters as much as having one of
                # each. The app sends the photos first and the voice note last,
                # so a recording means the capture is complete; a typed
                # description arrives with the listing and says nothing about
                # how many photos are still in flight, which is what the
                # expected count is for. Starting early left the artisan's
                # second and third photos unprocessed - still the raw camera
                # frames - while the first was composited.
                expected = db_listing.expected_photo_count
                have_all_photos = (
                    has_audio or not expected or photo_count >= expected
                )
                if has_photo and has_account and have_all_photos:
                    background_tasks.add_task(
                        process_listing,
                        listing_id=db_listing.id,
                        seller_id=current_seller.id,
                    )

    return MediaUploadResponse(
        id=str(stored.media_id),
        listing_id=listing_id,
        media_type=media_type,
        status="uploaded",
    )


@router.get(
    "/{listing_id}/media/{media_id}",
    status_code=status.HTTP_200_OK,
    summary="Fetch Listing Media",
    description="Serve a stored image or audio file belonging to the authenticated seller's listing.",
    responses={200: {"content": {"image/jpeg": {}}, "description": "The stored media file."}},
)
def get_listing_media(
    listing_id: str,
    media_id: str,
    current_seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Serve one stored media file.

    The app needs real URLs for the photos it uploaded, and these are an
    artisan's own pictures, so the file is served only to the seller who owns
    the listing rather than from a public static mount.
    """
    try:
        media_uuid = uuid.UUID(media_id)
        listing_uuid = uuid.UUID(listing_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Media not found."
        )

    media = (
        db.query(Media)
        .filter(Media.id == media_uuid, Media.listing_id == listing_uuid)
        .first()
    )
    if media is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Media not found."
        )

    listing = db.query(Listing).filter(Listing.id == media.listing_id).first()
    if listing is None or listing.seller_id != current_seller.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Media not found."
        )

    # Resolve inside the media root: a stored path must never be able to reach
    # an arbitrary file on the host.
    base_dir = Path(settings.MEDIA_STORAGE_DIR).resolve()

    # Prefer the Vision Station's studio image. This URL is the only one the app
    # ever sees - it is what the review screen, the preview and the published
    # listing all render - so serving the raw camera frame here meant the
    # grading, cutout and compositing never reached the buyer. The original is
    # still on disk and still what a re-run reads, and it is served here as the
    # fallback whenever a run has not produced a composite or the composite has
    # gone missing.
    path: Optional[Path] = None
    served_processed = False
    for candidate, is_processed in (
        (media.processed_path, True),
        (media.storage_path, False),
    ):
        if not candidate:
            continue
        try:
            resolved = (base_dir / candidate).resolve()
            if not resolved.is_relative_to(base_dir):
                raise ValueError("outside media root")
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            path = resolved
            served_processed = is_processed
            break

    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Media file is missing."
        )

    return FileResponse(
        path,
        # The composite is always written as JPEG, whatever the artisan's phone
        # uploaded, so the recorded upload type would be wrong for it.
        media_type=("image/jpeg" if served_processed else media.mime_type)
        or "application/octet-stream",
        # The artisan's own filename is right for their upload, but the
        # composite is a different file with a different extension.
        filename=path.name if served_processed else (media.original_filename or path.name),
    )
