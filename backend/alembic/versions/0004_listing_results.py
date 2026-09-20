"""Store what the pipeline understood about a listing.

Before this the pipeline computed a fact sheet, a price band and processed
images and then discarded all of it, recording only the listing's new state.
The read endpoints had nothing to answer from and returned hardcoded sample
data, so every listing read back as the same Madhubani painting.

Revision ID: 0004_listing_results
Revises: 0003_seller_craft_story
Create Date: 2026-09-18 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_listing_results"
down_revision: Union[str, None] = "0003_seller_craft_story"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # What the artisan typed instead of speaking. The description step offers a
    # keyboard as well as a microphone, and the pipeline reads this in place of
    # a transcript when there is no recording.
    op.add_column("listings", sa.Column("typed_description", sa.Text(), nullable=True))

    op.create_table(
        "listing_results",
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("material", sa.Text(), nullable=True),
        sa.Column("size", sa.Text(), nullable=True),
        sa.Column("colour", sa.Text(), nullable=True),
        sa.Column("technique", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("hours_to_make", sa.Float(), nullable=True),
        sa.Column("material_cost_in_paise", sa.Integer(), nullable=True),
        sa.Column(
            "is_one_of_a_kind",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        # Money is stored in paise so it never rides on a float.
        sa.Column("price_in_paise", sa.Integer(), nullable=True),
        sa.Column("suggested_price_in_paise", sa.Integer(), nullable=True),
        sa.Column("price_floor_in_paise", sa.Integer(), nullable=True),
        sa.Column("price_ceiling_in_paise", sa.Integer(), nullable=True),
        sa.Column("follow_up_question", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("craft_type", sa.Text(), nullable=True),
        sa.Column("story_summary", sa.Text(), nullable=True),
        sa.Column(
            "used_live_model",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
            name="fk_listing_results_listing_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("listing_id", name="pk_listing_results"),
    )


def downgrade() -> None:
    op.drop_table("listing_results")
    op.drop_column("listings", "typed_description")
