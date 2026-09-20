"""Local media storage service for validating, streaming, and storing uploaded media files."""
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.schemas.enums import MediaType

SAFE_LISTING_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")

# Conservative image MIME types and accepted extensions
ALLOWED_IMAGE_MIME_TYPES: Dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
}

ALLOWED_IMAGE_EXTENSIONS: Set[str] = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".heic",
    ".heif",
}

# Conservative audio MIME types and accepted extensions
ALLOWED_AUDIO_MIME_TYPES: Dict[str, str] = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/x-pn-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/m4a": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/x-aac": ".aac",
    "audio/ogg": ".ogg",
    "audio/vorbis": ".ogg",
    "audio/webm": ".webm",
}

ALLOWED_AUDIO_EXTENSIONS: Set[str] = {
    ".mp3",
    ".wav",
    ".m4a",
    ".mp4",
    ".aac",
    ".ogg",
    ".webm",
}


@dataclass
class StoredMediaResult:
    """Metadata result returned after successfully storing an uploaded media file."""

    media_id: uuid.UUID
    listing_id: str
    media_type: MediaType
    original_filename: Optional[str]
    storage_path: str
    dest_path: Path
    mime_type: str
    file_size_bytes: int


def validate_listing_id(listing_id: str) -> None:
    """Validate listing identifier to prevent path traversal and invalid characters."""
    if not listing_id or not SAFE_LISTING_ID_REGEX.match(listing_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid listing identifier: must be alphanumeric and may contain hyphens or underscores.",
        )


def get_listing_storage_dir(listing_id: str) -> Path:
    """Resolve and validate target directory for a listing within MEDIA_STORAGE_DIR."""
    validate_listing_id(listing_id)
    base_dir = Path(settings.MEDIA_STORAGE_DIR).resolve()
    target_dir = (base_dir / listing_id).resolve()
    try:
        target_dir.relative_to(base_dir)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid listing identifier: path traversal detected.",
        )
    return target_dir


def validate_media_content(
    media_type: MediaType,
    content_type: Optional[str],
    filename: Optional[str],
) -> str:
    """Validate content type and filename extension against strict allowlists.

    Returns the normalized safe extension (e.g. '.jpg', '.mp3') to use on disk.
    """
    raw_mime = (content_type or "").split(";")[0].strip().lower()
    raw_ext = Path(filename or "").suffix.lower()

    if media_type == MediaType.image:
        if raw_mime not in ALLOWED_IMAGE_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported image media type '{content_type or 'unknown'}'. Allowed formats: JPEG, PNG, WebP, HEIC.",
            )
        if raw_ext and raw_ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"File extension '{raw_ext}' is not permitted for image uploads.",
            )
        safe_ext = raw_ext if raw_ext in ALLOWED_IMAGE_EXTENSIONS else ALLOWED_IMAGE_MIME_TYPES[raw_mime]
        if safe_ext == ".jpeg":
            safe_ext = ".jpg"
        return safe_ext

    elif media_type == MediaType.audio:
        if raw_mime not in ALLOWED_AUDIO_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported audio media type '{content_type or 'unknown'}'. Allowed formats: MP3, WAV, M4A, AAC, OGG, WebM.",
            )
        if raw_ext and raw_ext not in ALLOWED_AUDIO_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"File extension '{raw_ext}' is not permitted for audio uploads.",
            )
        safe_ext = raw_ext if raw_ext in ALLOWED_AUDIO_EXTENSIONS else ALLOWED_AUDIO_MIME_TYPES[raw_mime]
        return safe_ext

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported logical media type '{media_type}'.",
        )


def delete_stored_file(path: Path) -> None:
    """Safely delete a stored file if it exists, suppressing filesystem errors."""
    try:
        if path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
    except Exception:
        pass


async def save_media_upload(
    file: UploadFile,
    media_type: MediaType,
    listing_id: str,
) -> StoredMediaResult:
    """Validate and stream an uploaded media file safely to local disk.

    Enforces:
    - Path traversal protection for listing_id and filename.
    - MIME type and extension validation against strict allowlists.
    - Chunk-by-chunk streaming to enforce MAX_MEDIA_UPLOAD_SIZE.
    - Rejection of empty (0-byte) files.
    - Server-controlled UUID storage names.
    - Automatic directory creation.
    - Cleanup of partial or failed file writes.
    """
    safe_ext = validate_media_content(media_type, file.content_type, file.filename)
    target_dir = get_listing_storage_dir(listing_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    media_id = uuid.uuid4()
    stored_filename = f"{media_id}{safe_ext}"
    dest_path = target_dir / stored_filename
    relative_storage_path = f"{listing_id}/{stored_filename}"

    chunk_size = 64 * 1024  # 64 KB
    total_bytes = 0

    try:
        with open(dest_path, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > settings.MAX_MEDIA_UPLOAD_SIZE:
                    f.close()
                    delete_stored_file(dest_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"File exceeds maximum allowed upload size of {settings.MAX_MEDIA_UPLOAD_SIZE} bytes.",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        delete_stored_file(dest_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to write media file to local disk.",
        ) from exc

    if total_bytes == 0:
        delete_stored_file(dest_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    original_filename = Path(file.filename).name[:512] if file.filename else None
    mime_type = (file.content_type or "").split(";")[0].strip().lower()

    return StoredMediaResult(
        media_id=media_id,
        listing_id=listing_id,
        media_type=media_type,
        original_filename=original_filename,
        storage_path=relative_storage_path,
        dest_path=dest_path,
        mime_type=mime_type,
        file_size_bytes=total_bytes,
    )
