"""Create domain tables for sellers, listings, media, listing_consents, suggestions, and listing_approvals.

Revision ID: 0001_domain_tables
Revises: None
Create Date: 2026-09-16 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_domain_tables"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # sellers table
    op.create_table(
        "sellers",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("cluster", sa.String(length=255), nullable=True),
        sa.Column("ondc_seller_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ondc_seller_id", name="uq_sellers_ondc_seller_id"),
    )

    # listings table
    op.create_table(
        "listings",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("seller_id", sa.Uuid(), nullable=False),
        sa.Column("client_item_id", sa.String(length=255), nullable=False),
        sa.Column(
            "state",
            sa.Enum("queued", "processing", "needs_attention", "ready", "published", name="listing_state"),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seller_id", "client_item_id", name="uq_listings_seller_client_item"),
    )
    op.create_index(op.f("ix_listings_seller_id"), "listings", ["seller_id"], unique=False)
    op.create_index(op.f("ix_listings_state"), "listings", ["state"], unique=False)

    # media table
    op.create_table(
        "media",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column(
            "media_type",
            sa.Enum("image", "audio", name="media_type"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(length=512), nullable=True),
        sa.Column("storage_path", sa.String(length=1024), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_media_listing_id"), "media", ["listing_id"], unique=False)

    # listing_consents table
    op.create_table(
        "listing_consents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("photo_consent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("story_consent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("listing_id", name="uq_listing_consents_listing_id"),
    )
    op.create_index(op.f("ix_listing_consents_listing_id"), "listing_consents", ["listing_id"], unique=False)

    # suggestions table
    op.create_table(
        "suggestions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("field", sa.String(length=255), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_suggestions_listing_id"), "suggestions", ["listing_id"], unique=False)

    # listing_approvals table
    op.create_table(
        "listing_approvals",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("listing_id", name="uq_listing_approvals_listing_id"),
    )
    op.create_index(op.f("ix_listing_approvals_listing_id"), "listing_approvals", ["listing_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_listing_approvals_listing_id"), table_name="listing_approvals")
    op.drop_table("listing_approvals")

    op.drop_index(op.f("ix_suggestions_listing_id"), table_name="suggestions")
    op.drop_table("suggestions")

    op.drop_index(op.f("ix_listing_consents_listing_id"), table_name="listing_consents")
    op.drop_table("listing_consents")

    op.drop_index(op.f("ix_media_listing_id"), table_name="media")
    op.drop_table("media")

    op.drop_index(op.f("ix_listings_state"), table_name="listings")
    op.drop_index(op.f("ix_listings_seller_id"), table_name="listings")
    op.drop_table("listings")

    op.drop_table("sellers")

    bind = op.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        sa.Enum(name="media_type").drop(bind, checkfirst=True)
        sa.Enum(name="listing_state").drop(bind, checkfirst=True)
