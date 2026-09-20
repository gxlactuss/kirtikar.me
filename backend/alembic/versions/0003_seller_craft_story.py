"""Add the artisan's own craft story to the sellers table.

Written once in the profile and reused across that seller's listings, where the
fact sheet stage may weave a single clause of it into the description.

Revision ID: 0003_seller_craft_story
Revises: 0002_firebase_authentication
Create Date: 2026-09-18 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_seller_craft_story"
down_revision: Union[str, None] = "0002_firebase_authentication"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sellers", sa.Column("craft_story", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("sellers", "craft_story")
