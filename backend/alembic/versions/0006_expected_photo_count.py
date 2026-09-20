"""Let a listing say how many photos its capture will send.

The app uploads files one at a time, so the server had no way to tell a pause
between photos from the end of the set. When the artisan typed their
description instead of recording it, the very first photo satisfied "a photo
and an account of the piece" and the run started immediately - the remaining
photos arrived milliseconds later, after the run had already read its media,
and were never graded or composited.

Revision ID: 0006_expected_photo_count
Revises: 0005_media_processed_path
Create Date: 2026-09-19 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0006_expected_photo_count"
down_revision: Union[str, None] = "0005_media_processed_path"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("expected_photo_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "expected_photo_count")
