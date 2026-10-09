"""Keep a copy of every demo run on storage that outlives the container.

The container's database and media folder are wiped each time it scales to
zero, which on the demo happens minutes after every visit, so without this
there is no way to look back at who used the demo or what they made.

With RUN_ARCHIVE_DIR set (an Azure Files share mounted into the container),
each listing gets a folder named by its IST creation time:

    2026-10-07_115242_<listing id>/
        visitor.json   who sent it: name if given, IP, browser, language
        run.json       what came out: the listing, transcript, raw attributes
        media/         the uploaded photo and voice note, and the studio image

Nothing here may raise. A full share or a dropped mount must never cost a
visitor their run, so every failure is logged and swallowed.
"""
import json
import logging
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Request
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.listing import Listing
from app.services.listing_view import to_listing_response

logger = logging.getLogger("app.services.run_archive")

IST = timezone(timedelta(hours=5, minutes=30))


def _run_dir(listing_id: uuid.UUID, created_at: datetime) -> Optional[Path]:
    if not settings.RUN_ARCHIVE_DIR:
        return None
    # SQLite hands timestamps back without a zone; they were written as UTC.
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    stamp = created_at.astimezone(IST).strftime("%Y-%m-%d_%H%M%S")
    path = Path(settings.RUN_ARCHIVE_DIR) / f"{stamp}_{listing_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def visitor_from(request: Request, name: Optional[str]) -> Dict[str, Any]:
    """What the request says about who sent it.

    Container Apps ingress puts the visitor's address first in
    X-Forwarded-For; the socket peer is the ingress proxy itself.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else None)
    return {
        "name": (name or "").strip() or None,
        "ip": ip,
        "user_agent": request.headers.get("user-agent"),
        "accept_language": request.headers.get("accept-language"),
        "referer": request.headers.get("referer"),
        "at": datetime.now(IST).isoformat(timespec="seconds"),
    }


def save_visitor(listing_id: uuid.UUID, created_at: datetime, visitor: Dict[str, Any]) -> None:
    try:
        run_dir = _run_dir(listing_id, created_at)
        if run_dir is not None:
            _write_json(run_dir / "visitor.json", visitor)
    except Exception:
        logger.exception("Listing %s -> could not archive the visitor", listing_id)


def write_run(listing: Listing) -> None:
    """Write the listing as it stands now, and any media not yet copied."""
    run_dir = _run_dir(listing.id, listing.created_at)
    if run_dir is None:
        return

    result = listing.result
    _write_json(
        run_dir / "run.json",
        {
            "listing": to_listing_response(listing).model_dump(mode="json"),
            "typed_description": listing.typed_description,
            "transcript": result.transcript if result else None,
            "language": result.language if result else None,
            "attributes": result.attributes if result else None,
            "archived_at": datetime.now(IST).isoformat(timespec="seconds"),
        },
    )

    media_root = Path(settings.MEDIA_STORAGE_DIR)
    media_dir = run_dir / "media"
    media_dir.mkdir(exist_ok=True)
    for item in listing.media:
        for stored in (item.storage_path, item.processed_path):
            if not stored:
                continue
            source = media_root / stored
            target = media_dir / source.name
            # Media files are named by id and never rewritten, so a copy that
            # is already there is the same file.
            if source.is_file() and not target.exists():
                shutil.copyfile(source, target)


def archive_run(listing_id: uuid.UUID) -> None:
    """write_run on a session of its own, for use after a response is sent."""
    if not settings.RUN_ARCHIVE_DIR:
        return
    db = SessionLocal()
    try:
        listing = db.query(Listing).filter(Listing.id == listing_id).first()
        if listing is not None:
            write_run(listing)
    except Exception:
        logger.exception("Listing %s -> could not archive the run", listing_id)
    finally:
        db.close()
