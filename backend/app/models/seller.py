import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.listing import Listing


class Seller(Base):
    """Seller entity representing an artisan registered in the publishing portal."""

    __tablename__ = "sellers"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    language: Mapped[str] = mapped_column(String(32), nullable=False, default="hi")
    cluster: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # The artisan's own story, written once in their profile and reused across
    # their listings as background for the description.
    craft_story: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ondc_seller_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    firebase_uid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
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

    __table_args__ = (
        UniqueConstraint("ondc_seller_id", name="uq_sellers_ondc_seller_id"),
        UniqueConstraint("firebase_uid", name="uq_sellers_firebase_uid"),
        UniqueConstraint("phone_number", name="uq_sellers_phone_number"),
    )

    # 1:N relationship with listings
    listings: Mapped[List["Listing"]] = relationship(
        "Listing",
        back_populates="seller",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
