import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.schemas.enums import MediaType

if TYPE_CHECKING:
    from app.models.listing import Listing


class Media(Base):
    """Media metadata entity representing photos or audio notes associated with a listing."""

    __tablename__ = "media"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    media_type: Mapped[MediaType] = mapped_column(
        sa.Enum(
            MediaType,
            name="media_type",
            native_enum=True,
            create_constraint=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    original_filename: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    storage_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    # Where the Vision Station wrote the graded, cut-out, composited version of
    # this photo, relative to the media root. The raw upload stays untouched in
    # storage_path so a re-run always starts from the original frame, but this
    # is the image the listing shows and publishes once a run has produced one.
    processed_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship to listing
    listing: Mapped["Listing"] = relationship("Listing", back_populates="media")
