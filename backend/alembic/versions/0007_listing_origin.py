"""Record where a listing was made.

The pipeline already asks the artisan for the origin when the voice note does
not mention it, but there was nowhere to keep the answer.

Revision ID: 0007_listing_origin
Revises: 0006_expected_photo_count
Create Date: 2026-09-19 13:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0007_listing_origin"
down_revision: Union[str, None] = "0006_expected_photo_count"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listing_results", sa.Column("origin", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("listing_results") as batch_op:
        batch_op.drop_column("origin")
