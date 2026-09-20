"""Persisted output of the listing pipeline.

The pipeline used to compute a fact sheet, a price band and a set of processed
images and then throw all of it away: only the listing's state was written back.
Every read endpoint therefore had to answer from hardcoded sample data, so an
artisan photographing a silver necklace was read back a Madhubani painting. This
table is where a run's conclusions live so the app can show what was actually
understood.
"""
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.listing import Listing


class ListingResult(Base):
    """One pipeline run's conclusions about one listing."""

    __tablename__ = "listing_results"

    listing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("listings.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # What the listing says
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # The fact sheet the artisan reviews and corrects
    material: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    size: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    colour: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    technique: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Where the artisan made it: their village, town or cluster.
    origin: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hours_to_make: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    material_cost_in_paise: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_one_of_a_kind: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )

    # Money is stored in paise so it never rides on a float
    price_in_paise: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    suggested_price_in_paise: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    price_floor_in_paise: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    price_ceiling_in_paise: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Set when a stage needs the artisan to answer something
    follow_up_question: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    craft_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    story_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Whether the facts came from a real model call or a synthetic fallback,
    # so a demo that silently degraded can be told from one that worked.
    used_live_model: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Everything else a stage produced, kept verbatim for debugging
    attributes: Mapped[Optional[Dict[str, Any]]] = mapped_column(sa.JSON, nullable=True)

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

    listing: Mapped["Listing"] = relationship("Listing", back_populates="result")
